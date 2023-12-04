import os
import torch
import numpy as np
import pickle as pkl
import networkx as nx
import scipy.sparse as sp

from torch_sparse import SparseTensor
from torch_geometric.utils import from_networkx, mask_to_index

from sgl.sampler.base_sampler import NodeWiseSampler, LayerWiseSampler, GraphWiseSampler


class NeighborSampler(NodeWiseSampler):
    def __init__(self, adj, **kwargs):
        """
        Neighborhood sampler
        """
        super(NeighborSampler, self).__init__(adj, **kwargs)
        self.sampler_name = "NeighborSampler"
        self.sample_level = "node"
        self.pre_sampling = False
    
    def collate_fn(self, batch_inds):
        """
        Input:
            batch_inds: array of batch node inds
        Method:
            Neighborhood sampling
        Outputs:
            batch_in: global node index of each source node in the first aggregation layer
            batch_out: global node index of each target node in the last aggregation layer
            block: sampled adjs in the form of sparse tensors wrapped in Block class
        """
        if callable(batch_inds):
            batch_inds = batch_inds()
        if isinstance(batch_inds, torch.Tensor):
            batch_inds = batch_inds.numpy()
        if not isinstance(batch_inds, np.ndarray):
            batch_inds = np.asarray(batch_inds)
        
        all_adjs = []

        cur_tgt_nodes = batch_inds    
        for layer_index in range(self.num_layers):
            cur_src_nodes, adj_sampled = self.one_layer_sampling(cur_tgt_nodes, self.layer_sizes[layer_index], True)
            all_adjs.insert(0, adj_sampled)
            cur_tgt_nodes = cur_src_nodes
        
        all_adjs = self._post_process(all_adjs, to_sparse_tensor=False)
     
        return cur_tgt_nodes, batch_inds, self._to_Block(all_adjs)  

class FastGCNSampler(LayerWiseSampler):
    def __init__(self, adj, **kwargs):   
        super(FastGCNSampler, self).__init__(adj, **kwargs) 
        self.sampler_name = "FastGCNSampler"
        self.sample_level = "layer"
        self.pre_sampling = False

    def collate_fn(self, batch_inds): 
        """
        Input:
            batch_inds: array of batch node inds
        Method:
            Sample fixed size of nodes independently at each layer.
        Outputs:
            batch_in: global node index of each source node in the first aggregation layer
            batch_out: global node index of each target node in the last aggregation layer
            block: sampled adjs in the form of sparse tensors wrapper in Block class
        """
        if callable(batch_inds):
            batch_inds = batch_inds()
        if not isinstance(batch_inds, np.ndarray):
            batch_inds = np.asarray(batch_inds)
        all_adjs = []

        cur_out_nodes = batch_inds
        for layer_index in range(self.num_layers):
            cur_in_nodes, cur_adj = self.one_layer_sampling(
                cur_out_nodes, self.layer_sizes[layer_index], self.probs)
            all_adjs.insert(0, cur_adj)
            cur_out_nodes = cur_in_nodes

        all_adjs = self._post_process(all_adjs, to_sparse_tensor=False)

        return cur_out_nodes, batch_inds, self._to_Block(all_adjs)
    
class ClusterGCNSampler(GraphWiseSampler):
    """
    Clustering the graph, feature set and target.
    """
    def __init__(self, dataset, **kwargs):
        """
        Inputs:
            adj: Adjacency matrix (Networkx Graph).
        """
        super(ClusterGCNSampler, self).__init__(nx.from_scipy_sparse_matrix(dataset.adj), **kwargs)
        self.sampler_name = "ClusterGCNSampler"
        self.sample_level = "graph"
        self.pre_sampling = True # conduct sampling only once before training
        self.sampling_done = False
        self._masks = {"train": dataset.train_mask, "val": dataset.val_mask, "test": dataset.test_mask}

    @property 
    def sample_graph_ops(self):
        if self.cluster_method == "metis":
            return self._metis_clustering
        else:
            raise NotImplementedError

    def _pre_process(self, **kwargs):
        
        self.cluster_method = kwargs.get("cluster_method", "metis")
        self.cluster_number = kwargs.get("cluster_number", 32)
        
        self._save_dir = kwargs.get("save_dir", None)
        if self._save_dir is not None:
            self._save_path_pt = os.path.join(self._save_dir, f"cluster_partition_{self.cluster_method}_{self.cluster_number}.pt")
            self._save_path_pkl = os.path.join(self._save_dir, f"cluster_partition_{self.cluster_method}_{self.cluster_number}.pkl")
        else:
            self._save_path_pt = self._save_path_pkl = None

    def collate_fn(self, batch_inds, mode):
        if not isinstance(batch_inds, torch.Tensor):
            batch_inds = torch.tensor(batch_inds)
        
        # stack len(batch_inds) subgraphs into one graph
        start = self.partptr[batch_inds].tolist()
        end = self.partptr[batch_inds + 1].tolist()
        node_idx = torch.cat([torch.arange(s, e) for s, e in zip(start, end)])
        global_node_idx = self.perm_node_idx[node_idx]
        composed_sparse_mx = sp.block_diag([self.splitted_perm_adjs[batch_ind.item()] for batch_ind in batch_inds])
        block = self._to_Block(composed_sparse_mx)
        if mode in ["train", "val", "test"]:
            mask = self._masks[mode][global_node_idx]
            global_inds = global_node_idx[mask]
            local_inds = mask_to_index(mask)
            batch_out = torch.vstack([local_inds, global_inds])
        else:
            mode = mode.split("_")
            batch_out = {}
            for one_mode in mode:
                mask = self._masks[one_mode][global_node_idx]
                global_inds = global_node_idx[mask]
                local_inds = mask_to_index(mask)
                batch_out.update({one_mode: torch.vstack([local_inds, global_inds])})
        return global_node_idx, batch_out, block

    def _metis_clustering(self):
        data = from_networkx(self._adj)
        N, E = data.num_nodes, data.num_edges
        adj = SparseTensor(
            row=data.edge_index[0], col=data.edge_index[1],
            value=torch.arange(E, device=data.edge_index.device),
            sparse_sizes=(N, N))
        self.perm_adjs, self.partptr, self.perm_node_idx = adj.partition(self.cluster_number, False) 
        self.splitted_perm_adjs = []
        for i in range(len(self.partptr)-1):
            start, end = self.partptr[i], self.partptr[i+1]
            node_idx = torch.arange(start, end)
            perm_adj = self.perm_adjs.narrow(0, start, end-start)
            perm_adj = perm_adj.index_select(1, node_idx)
            row, col, _ = perm_adj.coo()
            row, col = row.numpy(), col.numpy()
            num_nodes = len(node_idx)
            sparse_mx = sp.coo_matrix((np.ones_like(row), (row, col)), shape=(num_nodes, num_nodes))
            sparse_mx = self._post_process(sparse_mx, to_sparse_tensor=False)
            self.splitted_perm_adjs.append(sparse_mx)
        if self._save_dir is not None:
            torch.save((self.perm_adjs, self.partptr, self.perm_node_idx), self._save_path_pt)
            pkl.dump(self.splitted_perm_adjs, open(self._save_path_pkl, "wb"))
            print(f"\nSave Metis graph clustering results under the {self._save_dir} directory.\n")

class GraphSAINTSampler(BaseSampler):
    '''
        sample the wholo graph, feature and label as GraphSAINT method
    '''
    def __init__(self, adj, **kwargs):
        """
        Inputs:
            adj: adj of dgl Graph:sp.matrix
            kwargs: some params
        """
        self.replace = True
        self.node_budget = kwargs['nodebudget']

        super(GraphSAINTSampler, self).__init__(adj, **kwargs)

        self.sampler_name = "GraphSaintSampler"
        self.sample_level = "graph"
        self.pre_sampling = False

    def _pre_process(self, **kwargs):
        if kwargs['samplertype'] == "Node":
            self._calc_probs(**kwargs)
            self.sample = self.node_sample
        else:
            raise NotImplementedError

        self._calc_norm(**kwargs)

    def node_sample(self):
        """
        Inputs:
            batch_ids: is not used in this method

        method: sample fixed size of nodes as a subgraph

        Outputs:
            batch_in: global node index
            batch_out: global node index
            block: sampled adjs in the form of sparse tensors wrapped in Block class
        """

        p = self.probs
        sampled = np.random.choice(np.arange(np.size(p)), self.node_budget, self.replace, p)
        sampled = np.unique(sampled)

        adj = self._adj[sampled, :].tocsc()
        adj = adj[:, sampled].tocsr()
        return sampled, adj

    def _calc_norm(self, **kwargs):
        """
        methods: calculate the norm to estimate embedding and loss
        """
        times = kwargs['pre_sampling_graphs']

        node_value = np.zeros(np.size(self.probs))
        edge_value = sp.lil_matrix((np.size(self.probs),np.size(self.probs)))

        for _ in range(times):
            sampled, adj = self.sample()
            adj = adj.tocoo()
            for row, col in zip(adj.row, adj.col):
                edge_value[sampled[row],sampled[col]] += 1
            node_value[sampled] += 1

        edge_value = edge_value.tocsr().dot(sp.diags(1.0 / np.maximum(node_value, 1)))
        
        self.aggr_norm = edge_value
        self.loss_norm = torch.FloatTensor(np.maximum(node_value, 1))
        return

    def collate_fn(self, batch_ids):
        """
        Inputs: 
            batch_ids: is not used in this method

        method: sample fixed size of nodes as a subgraph
        
        Outputs: batch_in: global node index
                 batch_out: global node index
                 block: sampled adjs in the form of sparse tensors wrapped in Block class
        """
        sampled, adj = self.sample()
        sampled_aggr_norm = self.aggr_norm[sampled, :].tocsc()
        sampled_aggr_norm = sampled_aggr_norm[:, sampled]
        adj = adj.multiply(sampled_aggr_norm.transpose())

        self.index = sampled

        return sampled,sampled,self._to_Block(adj)