from .node_classification import HeteroNodeClassification
from .node_classification import NodeClassification
from .node_classification_sampling import NodeClassification_Sampling, NodeClassification_RecycleSampling
from .node_clustering import NodeClustering
from .node_clustering import NodeClusteringNAFS
from .link_prediction import LinkPredictionGAE
from .link_prediction import LinkPredictionNAFS
from .correct_and_smooth import NodeClassification_With_CorrectAndSmooth
from .node_classification_with_label_use import NodeClassificationWithLabelUse
from .node_classification_dist import NodeClassificationDist
from .node_classification_GAug import NodeClassificationGAugO, NodeClassificationGAugM

__all__ = [
    "NodeClassification",
    "HeteroNodeClassification",
    "NodeClustering",
    "NodeClusteringNAFS",
    "LinkPredictionGAE",
    "LinkPredictionNAFS",
    "NodeClassification_With_CorrectAndSmooth",
    "NodeClassificationWithLabelUse",
    "NodeClassificationDist",
    "NodeClassification_Sampling",
    "NodeClassification_RecycleSampling",
    "NodeClassificationGAugO",
    "NodeClassificationGAugM"
]
