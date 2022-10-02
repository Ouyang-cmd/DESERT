import numpy as np
from rdkit.Chem import rdMolTransforms
from rdkit import Chem
from .common import ATOM_RADIUS, ATOMIC_NUMBER, ATOMIC_NUMBER_REVERSE
from math import ceil, pi
from .tfbio_data import make_grid, ROTATIONS
import random
import copy
from skimage.util import view_as_blocks
from .tfbio_data import rotation_matrix
from .fragmenizer import BRICS_RING_R_Fragmenizer

fragmenizer = BRICS_RING_R_Fragmenizer()

def get_mol_centroid(mol, confId=-1):
    conformer = mol.GetConformer(confId)
    centroid = np.mean(conformer.GetPositions(), axis=0)
    return centroid

def trans(x, y, z):
    translation = np.eye(4)
    translation[:3, 3] = [x, y, z]
    return translation

def centralize(mol, confId=-1):
    conformer = mol.GetConformer(confId)
    centroid = get_mol_centroid(mol, confId)
    translation = trans(-centroid[0], -centroid[1], -centroid[2])  
    rdMolTransforms.TransformConformer(conformer, translation)
    return mol

def get_atom_stamp(grid_resolution, max_dist):
    # atom stamp is a sphere which radius equal to atom van der Waals radius
    def _get_atom_stamp(symbol):
        box_size = ceil(2 * max_dist // grid_resolution + 1)

        x, y, z = np.indices((box_size, box_size, box_size))
        x = x * grid_resolution + grid_resolution / 2
        y = y * grid_resolution + grid_resolution / 2
        z = z * grid_resolution + grid_resolution / 2

        mid = (box_size // 2, box_size // 2, box_size // 2)
        mid_x = x[mid]
        mid_y = y[mid]
        mid_z = z[mid]

        sphere = (x - mid_x)**2 + (y - mid_y)**2 + (z - mid_z)**2 \
            <= ATOM_RADIUS[symbol]**2
        sphere = sphere.astype(int)
        sphere[sphere > 0] = ATOMIC_NUMBER[symbol]
        return sphere

    atom_stamp = {}
    for symbol in ATOM_RADIUS:
        atom_stamp[symbol] = _get_atom_stamp(symbol)
    return atom_stamp

def get_atom_stamp_with_noise(grid_resolution, max_dist, mu, sigma):
    def _get_atom_stamp_with_noise(symbol, mu, sigma):
        box_size = ceil(2 * max_dist // grid_resolution + 1)

        x, y, z = np.indices((box_size, box_size, box_size))
        x = x * grid_resolution + grid_resolution / 2
        y = y * grid_resolution + grid_resolution / 2
        z = z * grid_resolution + grid_resolution / 2

        mid = (box_size // 2, box_size // 2, box_size // 2)
        mid_x = x[mid]
        mid_y = y[mid]
        mid_z = z[mid]

        noise = np.random.normal(loc=mu, scale=sigma)
        if noise < 0:
            noise = 0 

        sphere = (x - mid_x)**2 + (y - mid_y)**2 + (z - mid_z)**2 \
            <= (ATOM_RADIUS[symbol] + noise)**2
        sphere = sphere.astype(int)
        sphere[sphere > 0] = ATOMIC_NUMBER[symbol]
        return sphere
    
    atom_stamp = {}
    for symbol in ATOM_RADIUS:
        atom_stamp[symbol] = _get_atom_stamp_with_noise(symbol, mu, sigma)
    return atom_stamp

def get_binary_features(mol, confId):
    coords = []
    features = []
    confermer = mol.GetConformer(confId)
    for atom in mol.GetAtoms():
        if atom.HasProp('mask') and get_atom_prop(atom, 'mask') == 'true':
            continue
        idx = atom.GetIdx()
        coord = list(confermer.GetAtomPosition(idx))
        coords.append(coord)
        features.append(atom.GetAtomicNum())
    coords = np.array(coords)
    features = np.array(features)
    features = np.expand_dims(features, axis=1)
    return coords, features

def get_shape(mol, atom_stamp, grid_resolution, max_dist, confId=-1):
    # expand each atom point to a sphere
    coords, features = get_binary_features(mol, confId)
    grid, atomic2grid = make_grid(coords, features, grid_resolution, max_dist)
    shape = np.zeros(grid[0, :, :, :, 0].shape)
    for tup in atomic2grid:
        atomic_number = int(tup[0])
        stamp = atom_stamp[ATOMIC_NUMBER_REVERSE[atomic_number]]
        for grid_ijk in atomic2grid[tup]:
            i = grid_ijk[0]
            j = grid_ijk[1]
            k = grid_ijk[2]

            x_left = i - stamp.shape[0] // 2 if i - stamp.shape[0] // 2 > 0 else 0
            x_right = i + stamp.shape[0] // 2 if i + stamp.shape[0] // 2 < shape.shape[0] else shape.shape[0] - 1
            x_l = i - x_left
            x_r = x_right - i

            y_left = j - stamp.shape[1] // 2 if j - stamp.shape[1] // 2 > 0 else 0
            y_right = j + stamp.shape[1] // 2 if j + stamp.shape[1] // 2 < shape.shape[1] else shape.shape[1] - 1
            y_l = j - y_left
            y_r = y_right - j

            z_left = k - stamp.shape[2] // 2 if k - stamp.shape[2] // 2 >0 else 0
            z_right = k + stamp.shape[2] // 2 if k + stamp.shape[2] // 2 < shape.shape[2] else shape.shape[2] - 1
            z_l = k - z_left
            z_r = z_right - k

            mid = stamp.shape[0] // 2
            shape_part =  shape[x_left: x_right + 1, y_left: y_right + 1, z_left: z_right + 1]
            stamp_part = stamp[mid - x_l: mid + x_r + 1, mid - y_l: mid + y_r + 1, mid - z_l: mid + z_r + 1]

            shape_part += stamp_part
    shape[shape > 0] = 1
    return shape

def sample_augment(sample, rotation_bin, max_translation, confId=-1):
    sample = copy.deepcopy(sample)
    confermer = sample['mol'].GetConformer(confId)

    rot = random.choice(range(rotation_bin))
    rotation_mat = ROTATIONS[rot]

    # rotation the molecule
    rotation = np.zeros((4, 4))
    rotation[:3, :3] = rotation_mat
    rdMolTransforms.TransformConformer(confermer, rotation)

    # rotation fragments
    for fragment in sample['frag_list']:
        frag_rotation_mat = fragment['rotate_mat']
        frag_trans_vec = fragment['trans_vec']
        
        frag_rotation_translation = np.zeros((4, 4))
        frag_rotation_translation[:3, :3] = frag_rotation_mat
        frag_rotation_translation[:3, 3] = frag_trans_vec

        frag_rotation_translation_rotation = np.dot(rotation, frag_rotation_translation)

        fragment['rotate_mat'] = frag_rotation_translation_rotation[:3, :3]
        fragment['trans_vec'] = frag_rotation_translation_rotation[:3, 3]

    tr = max_translation * np.random.rand(3)

    # translate the molecule
    translate = trans(tr[0], tr[1], tr[2])
    rdMolTransforms.TransformConformer(confermer, translate)

    # translate fragments
    for fragment in sample['frag_list']:
        frag_trans_vec = fragment['trans_vec']
        frag_trans_vec = frag_trans_vec + tr
        fragment['trans_vec'] = frag_trans_vec

    return sample

def get_shape_patches(shape, patch_size):
    assert shape.shape[0] % patch_size == 0
    shape_patches = view_as_blocks(shape, (patch_size, patch_size, patch_size))
    return shape_patches

def time_shift(s):
    return s[:-1], s[1:]

def get_grid_coords(coords, max_dist, grid_resolution):
    grid_coords = (coords + max_dist) / grid_resolution
    grid_coords = grid_coords.round().astype(int)
    return grid_coords

def get_rotation_bins(sp, rp):
    mid = sp // 2
    sr = 1.0 / sp

    face1 = []
    for y in range(sp):
        for z in range(sp):
            face1.append(np.array([0.5, (y - mid) * sr, (z - mid) * sr]))
    face2 = []
    for x in range(sp):
        for y in range(sp):
            face2.append(np.array([(x - mid) * sr, (y - mid) * sr, 0.5]))
    face3 = []
    for x in range(sp):
        for z in range(sp):
            face3.append(np.array([(x - mid) * sr, 0.5, (z - mid) * sr]))
    
    face_point = face1 + face2 + face3
    
    rotation_mat_bin = [rotation_matrix(np.array((1, 1, 1)), 0)]
    for p in face_point:
        for t in range(1, rp):
            axis = p
            theta = t * pi / (rp / 2)
            rotation_mat_bin.append(rotation_matrix(axis, theta))
    rotation_mat_bin = np.stack(rotation_mat_bin, axis=0)

    return rotation_mat_bin

def set_atom_prop(atom, prop_name, prop_value):
    atom.SetProp(prop_name, prop_value)

def get_atom_prop(atom, prop_name):
    if atom.HasProp(prop_name):
        return atom.GetProp(prop_name)
    else:
        return None

def real_tree_len(tree, special_tokens):
    cnt = 0
    for item in tree:
        if isinstance(item[0], str) and item[0].lower() in special_tokens:
            continue
        cnt += 1
    return cnt

def get_partial_tree(tree, mask_len):
    mask_len = mask_len + 1 # EOS will take one spot
    partial_tree = tree[:-mask_len]
    partial_tree.append(('EOS', None, None))
    remove_parts = tree[-mask_len:]
    return partial_tree, remove_parts

def mask_frags(mol, frag_list, mask_frags_idx):
    curr_frags, _ = fragmenizer.fragmenize(mol)
    curr_frags = Chem.GetMolFrags(curr_frags, asMols=True)
    curr_cen_f_idx_mapping = {}
    for f_idx, frag in enumerate(curr_frags):
        curr_cen = tuple(get_mol_centroid(frag).round(2))
        curr_cen_f_idx_mapping[curr_cen] = f_idx
    
    list_cen_f_idx_mapping = {}
    for f_idx, item in enumerate(frag_list):
        cen = tuple(item['trans_vec'].round(2))
        list_cen_f_idx_mapping[cen] = f_idx

    assert len(curr_cen_f_idx_mapping) == len(list_cen_f_idx_mapping)

    list_curr_mapping = {}
    for cen in list_cen_f_idx_mapping:
        try:
            assert cen in curr_cen_f_idx_mapping
            list_curr_mapping[list_cen_f_idx_mapping[cen]] = curr_cen_f_idx_mapping[cen]
        except:
            list_curr_mapping[list_cen_f_idx_mapping[cen]] = list_cen_f_idx_mapping[cen]
    
    for m_f_idx in mask_frags_idx:
        curr_frag = curr_frags[list_curr_mapping[m_f_idx]]
        for atom in curr_frag.GetAtoms():
            origin_atom_idx = get_atom_prop(atom, 'origin_atom_idx')
            if origin_atom_idx is None:
                continue
            origin_atom_idx = int(origin_atom_idx)
            origin_atom = mol.GetAtomWithIdx(origin_atom_idx)
            set_atom_prop(origin_atom, 'mask', 'true')
    
    return mol
