import torch
from torch import Tensor
import numpy as np
import scipy.sparse as sp
from scipy.sparse import csr_matrix
from torch_sparse import SparseTensor
from torch_geometric.utils import from_scipy_sparse_matrix
from sgl.utils import sparse_mx_to_torch_sparse_tensor, sparse_mx_to_pyg_sparse_tensor

# A lighter wrapper class for sampled adjacency matrices, 
# as the Edge class seems contains useless information
class Block:
    def __init__(self, adjs, sparse_type):
        self.__sparse_type = sparse_type
        if not isinstance(adjs, list):
            self.__adjs = [adjs]
            if isinstance(adjs, SparseTensor):
                self.__root_sizes = [adjs.sparse_size(0)]
            else:
                self.__root_sizes = [adjs.shape[0]]
        else:
            self.__adjs = adjs
            if isinstance(adjs[0], SparseTensor):
                self.__root_sizes = [adj.sparse_size(0) for adj in adjs]
            else:
                self.__root_sizes = [adj.shape[0] for adj in adjs]
        self.__device = None
   
    def __len__(self):
        return len(self.__adjs)
    
    def __iter__(self):
        for adj in self.__adjs:
            yield adj

    def __getitem__(self, id):
        return self.__adjs[id]
    
    def root_size(self, id):
        return self.__root_sizes[id]

    def to_device(self, device):
        if self.__device == device:
            return
        if isinstance(self.__adjs[0], sp.spmatrix):
            if self.__sparse_type == "pyg":
                self.__adjs = [sparse_mx_to_pyg_sparse_tensor(adj) for adj in self.__adjs]
            elif self.__sparse_type == "torch":
                self.__adjs = [sparse_mx_to_torch_sparse_tensor(adj) for adj in self.__adjs]
            else:
                self.__adjs = [from_scipy_sparse_matrix(adj)[0] for adj in self.__adjs]
        self.__adjs = [adj.to(device) for adj in self.__adjs]
        self.__device = device


# Base class for adjacency matrix
class Edge:
    def __init__(self, row, col, edge_weight, edge_type, num_node, edge_attrs=None):
        if not isinstance(edge_type, str):
            raise TypeError("Edge type must be a string!")
        self.__edge_type = edge_type

        if (not isinstance(row, (list, np.ndarray, Tensor))) or (not isinstance(col, (list, np.ndarray, Tensor))) or (
                not isinstance(edge_weight, (list, np.ndarray, Tensor))):
            raise TypeError("Row, col and edge_weight must be a list, np.ndarray or Tensor!")
        if not isinstance(row, Tensor):
            row = torch.LongTensor(row)
        if not isinstance(col, Tensor):
            col = torch.LongTensor(col)
        if not isinstance(edge_weight, Tensor):
            edge_weight = torch.FloatTensor(edge_weight)
        self.__row = row
        self.__col = col
        self.__edge_weight = edge_weight
        self.__edge_attrs = edge_attrs
        self.__num_edge = len(row)

        self.__sparse_matrix = csr_matrix((edge_weight.numpy(), (row.numpy(), col.numpy())),
                                              shape=(num_node, num_node))

    @property
    def sparse_matrix(self):
        return self.__sparse_matrix
    
    @property
    def edge_type(self):
        return self.__edge_type

    @property
    def num_edge(self):
        return self.__num_edge

    @property
    def edge_index(self):
        return self.__row, self.__col

    @property
    def edge_attrs(self):
        return self.__edge_attrs

    @edge_attrs.setter
    def edge_attrs(self, edge_attrs):
        # more restrictions

        self.__edge_attrs = edge_attrs

    @property
    def row(self):
        return self.__row

    @property
    def col(self):
        return self.__col

    @property
    def edge_weight(self):
        return self.__edge_weight


# Base class or storing node information
class Node:
    def __init__(self, node_type, num_node, x=None, y=None, node_ids=None):
        if not isinstance(num_node, int):
            raise TypeError("Num nodes must be a integer!")
        if not isinstance(node_type, str):
            raise TypeError("Node type must be a string!")
        if (node_ids is not None) and (not isinstance(node_ids, (list, np.ndarray, Tensor))):
            raise TypeError("Node IDs must be a list, np.ndarray or Tensor!")
        self.__num_node = num_node
        self.__node_type = node_type
        if node_ids is not None:
            self.__node_ids = node_ids
        else:
            self.__node_ids = range(num_node)
        
        if x is not None:
            if isinstance(x, np.ndarray):
                x = torch.FloatTensor(x)   #这里是原始实现，但是是有bug的
            elif not isinstance(x, Tensor):
                raise TypeError("x must be a np.ndarray or Tensor!")
        self.__x = x
        
        if y is not None: 
            if isinstance(y, (list, np.ndarray)):
                y = torch.LongTensor(y)
            elif not isinstance(y, Tensor):
                raise TypeError("y must be a list, np.ndarray or Tensor!")
        self.__y = y

    @property
    def num_node(self):
        return self.__num_node

    @property
    def node_ids(self):
        return self.__node_ids

    @property
    def node_type(self):
        return self.__node_type

    @property
    def node_mask(self):
        return self.__node_mask

    @property
    def x(self):
        return self.__x

    @x.setter
    def x(self, x):
        # more restrictions
        if isinstance(x, np.ndarray):
            x = torch.FloatTensor(x)
        elif not isinstance(x, Tensor):
            raise TypeError("x must be a np.ndarray or Tensor!")
        self.__x = x

    @property
    def y(self):
        return self.__y

    @y.setter
    def y(self, y):
        # more restrictions
        if isinstance(y, (list, np.ndarray)):
            y = torch.LongTensor(y)
        elif not isinstance(y, Tensor):
            raise TypeError("y must be a list, np.ndarray or Tensor!")
        self.__y = y


# Base class for homogeneous graph
class Graph:
    def __init__(self, row, col, edge_weight, num_node, node_type, \
                    edge_type, x=None, y=None, node_ids=None, edge_attr=None):

        self.__edge = Edge(row, col, edge_weight, edge_type, num_node, edge_attr)
        self.__node = Node(node_type, num_node, x, y, node_ids)

    @property
    def num_node(self):
        return self.__node.num_node

    @property
    def num_edge(self):
        return self.__edge.num_edge

    @property
    def adj(self):
        return self.__edge.sparse_matrix
    
    @property
    def edge_index(self):
        return self.__edge.edge_index

    @property
    def edge_weight(self):
        return self.__edge.edge_weight

    @property
    def edge_attrs(self):
        return self.__edge.edge_attrs

    @property
    def edge_type(self):
        return self.__edge.edge_type

    @property
    def node_type(self):
        return self.__node.node_type

    @property
    def node_ids(self):
        return self.__node.node_ids
    
    @property
    def x(self):
        return self.__node.x

    @x.setter
    def x(self, x):
        self.__node.x = x

    @property
    def y(self):
        return self.__node.y

    @y.setter
    def y(self, y):
        self.__node.y = y

    @property
    def num_features(self):
        if self.__node.x is not None:
            return self.__node.x.shape[1]

    @property
    def num_classes(self):
        if self.__node.y is not None:
            return int(self.__node.y.max() + 1)

    @property
    def node_degrees(self):
        row_sum = self.adj.sum(axis=1)
        return torch.LongTensor(row_sum).squeeze(1)

    @property
    def node(self):
        return self.__node

    @node.setter
    def node(self, node):
        if not isinstance(node, Node):
            raise TypeError("node must be a Node!")
        self.__node = node

    @property
    def edge(self):
        return self.__edge

    @edge.setter
    def edge(self, edge):
        if not isinstance(edge, Edge):
            raise TypeError("edge must be an Edge!")
        self.__edge = edge


# Base class for heterogeneous graph
class HeteroGraph:
    def __init__(self, row_dict, col_dict, edge_weight_dict, num_node_dict, node_types, edge_types, node_id_dict,
                 x_dict=None, y_dict=None, edge_attr_dict=None):
        self.__nodes_dict = {}
        self.__node_types = node_types
        for node_type in node_types:
            if not isinstance(node_type, str):
                raise TypeError("Node type must be a string!")
        if not isinstance(num_node_dict, dict):
            raise TypeError("Num nodes must be a dict!")
        elif not isinstance(node_types, list):
            raise TypeError("Node types must be a list!")
        elif list(num_node_dict.keys()).sort() != node_types.copy().sort():
            raise TypeError("The keys of num_nodes and node_types must be the same!")
        elif ((x_dict is not None) and (not isinstance(x_dict, dict))) or (
                (y_dict is not None) and (not isinstance(y_dict, dict))):
            raise TypeError("Xs and Ys must be a dict!")

        self.__node_id_offsets = {}
        node_count = 0
        for node_type in node_types:
            self.__node_id_offsets[node_type] = node_count
            node_count += num_node_dict[node_type]

        if node_id_dict is None:
            self.__node_id_dict = {}
            for node_type in node_types:
                self.__node_id_dict[node_type] = list(range(self.__node_id_offsets[node_type],
                                                            self.__node_id_offsets[node_type] + num_node_dict[
                                                                node_type]))
        else:
            self.__node_id_dict = node_id_dict

        for node_type in node_types:
            self.__nodes_dict[node_type] = Node(node_type, num_node_dict[node_type], x_dict.get(node_type, None),
                                                y_dict.get(node_type, None), self.__node_id_dict[node_type])
                                                
        self.__edges_dict = {}
        self.__edge_types = edge_types
        for edge_type in edge_types:
            if not isinstance(edge_type, str):
                raise TypeError("Edge type must be a string!")
        if (not isinstance(row_dict, dict)) or (not isinstance(col_dict, dict)) or (
                not isinstance(edge_weight_dict, dict)) or (
                edge_attr_dict is not None and not isinstance(edge_attr_dict, dict)):
            raise TypeError("Rows, cols, edge weights and edge attrs must be dicts!")
        elif not isinstance(edge_types, list):
            raise TypeError("Edge types must be a list!")
        elif not ((row_dict.keys() == col_dict.keys()) and (col_dict.keys() == edge_weight_dict.keys()) and (
                list(edge_weight_dict.keys()).sort() == edge_types.copy().sort())):
            raise ValueError("The keys of the rows, cols, edge_weights and edge_types must be the same!")

        for edge_type in edge_types:
            if edge_attr_dict is not None:
                self.__edges_dict[edge_type] = Edge(row_dict[edge_type], col_dict[edge_type],
                                                    edge_weight_dict[edge_type], edge_type,
                                                    edge_attr_dict.get(edge_type, None))
            else:
                self.__edges_dict[edge_type] = Edge(row_dict[edge_type], col_dict[edge_type],
                                                    edge_weight_dict[edge_type], edge_type,
                                                    node_count)


    def __getitem__(self, key):
        if key in self.__edge_types:
            return self.__edges_dict[key]
        elif key in self.__node_types:
            return self.__nodes_dict[key]
        else:
            raise ValueError("Please input valid edge type or node type!")

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("Edge type or node type must be a string!")
        if key in self.__edge_types:
            if not isinstance(value, Edge):
                raise TypeError("Please organize the dataset using the Edge class!")
            # more restrictions

            self.__edges_dict[key] = value
        elif key in self.__node_types:
            if not isinstance(value, Node):
                raise TypeError("Please organize the dataset using the Node class!")
            # more restrictions

            self.__nodes_dict[key] = value
        else:
            raise ValueError("Please input valid edge type or node type!")

    @property
    def node_id_dict(self):
        return self.__node_id_dict

    @property
    def nodes(self):
        return self.__nodes_dict

    @property
    def node_types(self):
        return self.__node_types

    @property
    def edge_types(self):
        return self.__edge_types

    @property
    def edges(self):
        return self.__edges_dict

    @property
    def num_features(self):
        num_features = {}
        for node_type in self.__node_types:
            x_temp = self.__nodes_dict[node_type].x
            if x_temp is not None:
                num_features[node_type] = x_temp.shape[1]
            else:
                num_features[node_type] = 0
        return num_features

    @property
    def num_classes(self):
        num_classes = {}
        for node_type in self.__node_types:
            if self.__nodes_dict[node_type].y is not None:
                num_classes[node_type] = (self.__nodes_dict[node_type].y.max() + 1)
        return num_classes

    @property
    def num_node(self):
        num_node = {}
        for node_type in self.__node_types:
            num_node[node_type] = self.__nodes_dict[node_type].num_node
        return num_node
