import yaml
import argparse

import sgl.dataset as Dataset
from sgl.models.homo.gda import Mixup
from sgl.tasks import NodeClassification

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Mixup-Model.")
    parser.add_argument(
        "--device", type=int, default=0, help="gpu device id or cpu (-1)"
    )
    parser.add_argument(
        "--config_path", type=str, default="./configs/Mixup.yml", help="save path of the configuration file"
    )
    args = parser.parse_args()
    config = yaml.safe_load(open(args.config_path, "rb"))
    device = f"cuda:{args.device}" if args.device >= 0 else "cpu"
    dataset_kwargs = config["dataset"]
    model_kwargs = config["model"]
    task_kwargs = config["task"]

    dataset_classname = dataset_kwargs.pop("classname")
    dataset = getattr(Dataset, dataset_classname)(**dataset_kwargs)
    for seed in range(10):
        model = Mixup(in_dim=dataset.num_features, n_classes=dataset.num_classes, **model_kwargs)
        task_kwargs.update({"loss_fn": model.loss_fn})
        task_kwargs.update({"device": device})
        task_kwargs.update({"seed": seed})
        test_acc = NodeClassification(dataset, model, **task_kwargs).test_acc
        print(f"test acc: {test_acc:.4f}")