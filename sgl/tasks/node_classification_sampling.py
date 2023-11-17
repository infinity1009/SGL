import time
import torch
import numpy as np
from torch.optim import Adam
import torch.nn.functional as F
from torch.utils.data import DataLoader

from sgl.data.utils import RandomLoader, SplitLoader
from sgl.tasks.base_task import BaseTask
from sgl.tasks.utils import accuracy, set_seed, train, mini_batch_train, evaluate, mini_batch_evaluate


class NodeClassification_Sampling(BaseTask):
    def __init__(self, dataset, model, lr, weight_decay, epochs, device, loss_fn="nll_loss", seed=42,
                 train_batch_size=None, eval_batch_size=None):
        super(NodeClassification_Sampling, self).__init__()

        self.__dataset = dataset
        self.__labels = self.__dataset.y

        self.__model = model
        self.__optimizer = Adam(model.parameters(), lr=lr,
                                weight_decay=weight_decay)
        self.__epochs = epochs
        self.__loss_fn = getattr(F, loss_fn) if isinstance(loss_fn, str) else loss_fn
        self.__device = device
        self.__seed = seed
        self.__train_batch_size= train_batch_size
        self.__eval_batch_size = eval_batch_size
        self.__mini_batch_train = True if train_batch_size is not None else False
        self.__mini_batch_eval = True if eval_batch_size is not None else False
        self.__test_acc = self._execute()

    @property
    def test_acc(self):
        return self.__test_acc

    def _execute(self):
        set_seed(self.__seed)

        pre_time_st = time.time()
        self.__model.preprocess(adj=self.__dataset.adj, x=self.__dataset.x)
        pre_time_ed = time.time()
        print(f"Preprocessing done in {(pre_time_ed - pre_time_st):.4f}s")
        
        if self.__mini_batch_train:
            self.__train_loader = DataLoader(
                self.__dataset.train_idx, batch_size=self.__train_batch_size, shuffle=True, drop_last=False)
        if self.__mini_batch_eval:
            self.__val_loader = DataLoader(
                self.__dataset.val_idx, batch_size=self.__eval_batch_size, shuffle=False, drop_last=False)
            self.__test_loader = DataLoader(
                self.__dataset.test_idx, batch_size=self.__eval_batch_size, shuffle=False, drop_last=False)
            if self.__model.evaluate_mode == "full":
                self.__all_eval_loader = DataLoader(
                    range(self.__dataset.num_node), batch_size=self.__eval_batch_size, shuffle=False, drop_last=False)
            else:
                self.__all_eval_loader = DataLoader(
                    self.__dataset.test_idx, batch_size=self.__eval_batch_size, shuffle=False, drop_last=False)
                
        self.__model = self.__model.to(self.__device)
        self.__labels = self.__labels.to(self.__device)

        t_total = time.time()
        best_val = 0.
        best_test = 0.

        for epoch in range(self.__epochs):
            t = time.time()
            if self.__mini_batch_train:
                loss_train, acc_train = mini_batch_train(self.__model, self.__train_loader, self.__labels, self.__device, 
                                                         self.__optimizer, self.__loss_fn)
            else:
                loss_train, acc_train = train(self.__model, self.__dataset.train_idx, self.__labels, self.__device,
                                            self.__optimizer, self.__loss_fn)
            
            if self.__mini_batch_eval:
                acc_val, acc_test = mini_batch_evaluate(self.__model, self.__val_loader, self.__test_loader, 
                                                        self.__labels, self.__device)
            else:
                acc_val, acc_test = evaluate(self.__model, self.__dataset.val_idx, self.__dataset.test_idx,
                                            self.__labels, self.__device)

            print('Epoch: {:03d}'.format(epoch + 1),
                'loss_train: {:.4f}'.format(loss_train),
                'acc_train: {:.4f}'.format(acc_train),
                'acc_val: {:.4f}'.format(acc_val),
                'acc_test: {:.4f}'.format(acc_test),
                'time: {:.4f}s'.format(time.time() - t))

            if acc_val > best_val:
                best_val = acc_val
                best_test = acc_test

        acc_val, acc_test = self._postprocess()
        if acc_val > best_val:
            best_val = acc_val
            best_test = acc_test

        print("Optimization Finished!")
        print("Total time elapsed: {:.4f}s".format(time.time() - t_total))
        print(f'Best val: {best_val:.4f}, best test: {best_test:.4f}')
        return best_test

    def _postprocess(self):
        self.__model.eval()
        if self.__model.evaluate_mode == "full":
            if self.__mini_batch_eval is False:
                outputs = self.__model.model_forward(
                    range(self.__dataset.num_node), self.__device).to("cpu")
            else:
                outputs = []
                for batch in self.__all_eval_loader:
                    sample_dict = self.__model.sampling(batch)
                    output, batch = self.__model.model_forward(batch, self.__device, **sample_dict)
                    outputs.append(output)
                outputs = torch.vstack(outputs)

            # TODO: self.__model.postprocess now directly returns the original outputs
            final_output = self.__model.postprocess(self.__dataset.adj, outputs)
            acc_val = accuracy(
                final_output[self.__dataset.val_idx], self.__labels[self.__dataset.val_idx])
            acc_test = accuracy(
                final_output[self.__dataset.test_idx], self.__labels[self.__dataset.test_idx])           
        else:
            # ClusterGCN
            for batch in self.__all_eval_loader:
                outputs, labels = [], []
                for batch in self.__all_eval_loader:
                    sample_dict = self.__model.sampling(batch)
                    sample_dict.update({"ret_full": True})
                    output, batch = self.__model.model_forward(batch, self.__device, **sample_dict)
                    output = self.__model.postprocess(sample_dict["adj"], output)
                    outputs.append(output[batch])
                    labels.append(self.__labels[batch])
            outputs = torch.vstack(outputs)
            labels = torch.cat(labels)
            
            acc_val = accuracy(outputs, labels)
            acc_test = accuracy(outputs, labels)
        
        return acc_val, acc_test

class NodeClassification_RecycleSampling(BaseTask):
    def __init__(self, dataset, model, lr, weight_decay, num_iters, device, loss_fn="nll_loss", seed=42,
                 train_batch_size=1024, eval_batch_size=None,):
        super(NodeClassification_RecycleSampling, self).__init__()

        self.__dataset = dataset
        self.__labels = self.__dataset.y

        self.__model = model
        self.__optimizer = Adam(model.parameters(), lr=lr,
                                weight_decay=weight_decay)
        self.__num_iters = num_iters
        self.__loss_fn = getattr(F, loss_fn) if isinstance(loss_fn, str) else loss_fn
        self.__device = device
        self.__seed = seed
        self.__train_loader = RandomLoader(dataset.train_idx, train_batch_size)
        if eval_batch_size is not None:
           self.__val_loader = SplitLoader(dataset.val_idx, eval_batch_size)
           self.__test_loader = SplitLoader(dataset.test_idx, eval_batch_size)
           self.__eval_minibatch = True
        else:
           self.__val_loader = self.__test_loader = None
           self.__eval_minibatch = False
        self.__test_acc = self._execute()

    @property
    def test_acc(self):
        return self.__test_acc

    def _execute(self):
        set_seed(self.__seed)

        pre_time_st = time.time()
        self.__model.preprocess(adj=self.__dataset.adj, x=self.__dataset.x, val_dataloader=self.__val_loader, test_dataloader=self.__test_loader)
        pre_time_ed = time.time()
        print(f"Preprocessing done in {(pre_time_ed - pre_time_st):.4f}s")
        
        iter_cnt = 0
        val_score = 0
        best_val_score = 0

        torch.cuda.synchronize()
        train_time_st = time.time()
        taus = self.__model.generate_taus(self.__num_iters)

        iter_id = 0
        generator = self.__model.flash_sampling(len(taus), self.__train_loader)

        for sample_dict in generator:
            
            batch_out, batch_in, batch_adjs = sample_dict["batch_out"], sample_dict["batch_in"], sample_dict["sampled_adjs"]
            batch_x = self.__model.processed_feature[batch_in].to(self.__device)
            batch_y = self.__labels[batch_out].to(self.__device)
            batch_adjs = [adj.to(self.__device) for adj in batch_adjs]
            
            for rec_itr in range(taus[iter_id]):
                self.__optimizer.zero_grad()

                recycle_vector = None
                new_batch_x = batch_x 
                new_batch_y = batch_y
                new_batch_adjs = batch_adjs

                if rec_itr != 0:
                    recycle_vector = torch.cuda.FloatTensor(len(batch_out)).uniform_() > 0.2
                    new_batch_y = batch_y[recycle_vector]

                self.__model.train()
                pred = self.__model.model_forward(new_batch_x, new_batch_adjs)

                if recycle_vector is not None:
                    pred = pred[recycle_vector]

                loss = self.__loss_fn(pred, new_batch_y)
                loss.backward()
                self.__optimizer.step()

                val_score = self._validation(iter_cnt, prev_score=val_score)
                test_score = self._inference()
                
                if val_score > best_val_score:
                    best_val_score = val_score
                    best_test_score = test_score

                print('Iteration: {:03d}'.format(iter_cnt + 1),
                    'loss_train: {:.4f}'.format(loss),
                    'acc_val: {:.4f}'.format(val_score),
                    'acc_test: {:.4f}'.format(test_score))
                
                iter_cnt += 1

            iter_id += 1
        
        torch.cuda.synchronize()
        train_time_ed = time.time()
        print(f"Trianing done in {(train_time_ed - train_time_st):.4f}s")
        print(f'Best val acc: {best_val_score:.4f}')
        print(f'Best test acc: {best_test_score:.4f}')
        
        return best_test_score

    def _validation(self, iter_cnt, prev_score=None, val_freq=1):
        if (iter_cnt + 1) % val_freq == 0:
            self.__model.eval()
            if self.__eval_minibatch is False:
                val_y = self.__labels[self.__dataset.val_idx].to(self.__device)             
                val_pred = self.__model.model_forward(use_full=True)[self.__dataset.val_idx]
                val_score = accuracy(val_pred, val_y)
            else:
                val_scores = []
                val_sample_dicts = self.__model.val_sampling()
                for val_sample_dict in val_sample_dicts:
                    val_batch_out, val_batch_in, val_batch_adjs = val_sample_dict["batch_out"], val_sample_dict["batch_in"], val_sample_dict["sampled_adjs"]
                    val_batch_x = self.__model.processed_feature[val_batch_in].to(self.__device)
                    val_batch_y = self.__labels[val_batch_out].to(self.__device)
                    val_batch_adjs = [val_adj.to(self.__device) for val_adj in val_batch_adjs]

                    pred = self.__model.model_forward(val_batch_x, val_batch_adjs) 
                    val_score = accuracy(pred, val_batch_y)
                    val_batch_size = len(val_batch_out)
                    val_scores.append(val_score * val_batch_size)
                val_score = np.sum(val_scores) / len(self.__dataset.val_idx)
            return val_score
        else:
            return prev_score
        
    def _inference(self):
        self.__model.eval()
        if self.__eval_minibatch is False:
            test_y = self.__labels[self.__dataset.test_idx].to(self.__device, non_blocking=True)
            test_pred = self.__model.model_forward(use_full=True)[self.__dataset.test_idx]
            test_score = accuracy(test_pred, test_y)
        else:
            test_scores = []
            test_sample_dicts = self.__model.test_sampling()
            for test_sample_dict in test_sample_dicts:
                test_batch_out, test_batch_in, test_batch_adjs = test_sample_dict["batch_out"], test_sample_dict["batch_in"], test_sample_dict["sampled_adjs"]
                test_batch_x = self.__model.processed_feature[test_batch_in].to(self.__device)
                test_batch_y = self.__labels[test_batch_out].to(self.__device)
                test_batch_adjs = [test_adj.to(self.__device) for test_adj in test_batch_adjs]

                pred = self.__model.model_forward(test_batch_x, test_batch_adjs)
                test_score = accuracy(pred, test_batch_y)
                test_batch_size = len(test_batch_out)
                test_scores.append(test_score * test_batch_size) 
            test_score = np.sum(test_scores) / len(self.__dataset.test_idx)
        return test_score