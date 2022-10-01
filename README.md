# DESERT
Zero-Shot 3D Drug Design by Sketching and Generating (NeurIPS 2022)

<!-- ![](./pics/sketch_and_generate.png)
![](./pics/overview.png) -->
<div  align="center">    
<img src="./pics/sketch_and_generate.png"/>
</div>
<div  align="center">    
<img src="./pics/overview.png"/>
</div>

## Requirement
Our method is powered by an old version of [ParaGen](https://github.com/bytedance/ParaGen) (previous name ByCha).

Install it with
```bash
cd mybycha
pip install -e .
pip install horovod
pip install lightseq
```
You also need to install
```bash
conda install -c "conda-forge/label/cf202003" openbabel # recommend using anaconda for this project 
pip install rdkit-pypi
pip install pybel scikit-image pebble meeko==0.1.dev1 vina pytransform3d
```

## Pre-training

### Data Preparation

## Design Molecules

## Citation
```
@inproceedings{long2022DESERT,
  title={Zero-Shot 3D Drug Design by Sketching and Generating},
  author={Long, Siyu and Zhou, Yi and Dai, Xinyu and Zhou, Hao},
  booktitle={NeurIPS},
  year={2022}
}
```
