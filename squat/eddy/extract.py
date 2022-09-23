
"""
SQUAT: Study-wise QUality Assessment Tool

Extracts QC data from EDDY run - based on QUAD from EDDYQC

Matteo Bastiani, FMRIB, Oxford
Martin Craig, SPMIC, Nottingham
"""

import argparse
import os
import warnings
import numpy as np
import nibabel as nib
import logging
import json

from . import utils

warnings.filterwarnings("ignore")

LOG = logging.getLogger(__name__)

def _eddyfile(args, ext):
    return os.path.join(args.eddydir, args.eddybase + ext)

def _imgfile(fname):
    if not fname:
        return None
    img_fname = None
    for ext in ("", ".nii", ".nii.gz"):
        img_fname = fname + ext
        if os.path.isfile(img_fname):
            return img_fname

def main():
    """
    Generate QC report data for single subject dMRI data

    The script will look for EDDY output files that are generated according to the user
    specified options. If a feature (e.g., output the CNR maps) has not been used, then
    no data based on it will be produced

    The script produces a qc.json file that contains summery qc indices and basic 
    information about the data.

    The JSON file can then be read by squat to generate a group report.

    Output:
       output-dir/qc.pdf: single subject QC report 
       output-dir/qc.json: single subject QC and data info database
       output-dir/vols_no_outliers.txt: text file that contains the list of the non-outlier volumes (based on eddy residuals)
    """
    parser = argparse.ArgumentParser('SQUAT_EDDY - extract QC data from Eddy run', add_help=True)
    parser.add_argument('--eddydir', required=True, help='Path to directory containing EDDY output')
    parser.add_argument('--eddybase', help='Base name of EDDY output')
    parser.add_argument('--idx', required=True, help='Path to text file containing indices for all volumes into acquisition parameters relative to eddydir')
    parser.add_argument('--eddy-params', required=True, help='Path to file containing acquisition parameters relative to eddydir')
    parser.add_argument('--mask', required=True, help="Binary mask file")
    parser.add_argument('--bvals', required=True, help="BVALs file")
    parser.add_argument('--bvecs', help="BVECs file")
    parser.add_argument('--field', help="TOPUP estimated field (in Hz)")
    parser.add_argument('--slspec', help="Text file specifying slice/group acquisition")
    parser.add_argument('-o', '--output', help="Output directory - defaults to <eddydir>/qc")
    parser.add_argument('--overwrite', action="store_true", default=False, help='If specified, overwrite any existing output')
    args = parser.parse_args()

    #def extract(eddyBase, eddyIdx, eddyParams, mask, bvalsFile, bvecsFile, oDir, field, slspecFile, verbose):
    if not os.path.isdir(args.eddydir):
        raise ValueError(f"Not a directory: {args.eddydir}")
    print(f"Using EDDY directory: {args.eddydir}")
    
    eddy_files = os.listdir(args.eddydir)
    if not args.eddybase:
        for ext in (".eddy_parameters",):
            for fname in eddy_files:
                if fname.endswith(ext):
                    args.eddybase = fname[:-len(ext)]

    print(f"Using EDDY base name: {args.eddybase}")

    eddyfile = None
    for ext in (".nii", ".nii.gz"):
        eddyfile = _eddyfile(args, ext)
        if os.path.isfile(eddyfile):
            break

    if not eddyfile:
        raise ValueError(f'Could not find base image {args.eddydir}/{args.eddybase}')
    
    # EDDY INDICES
    try:
        eddyIdxs = np.genfromtxt(os.path.join(args.eddydir, args.idx), dtype=int)
    except Exception as exc:
        raise ValueError(f'Failed to read EDDY index file: {args.idx}: {exc}')

    # BVALS
    try:
        bvals = np.genfromtxt(os.path.join(args.eddydir, args.bvals), dtype=float)
    except Exception as exc:
        raise ValueError(f'Failed to read BVALS parameter file: {args.bvals}: {exc}')

    # MASK
    mask = _imgfile(os.path.join(args.eddydir, args.mask))
    if not mask:
        raise ValueError(f'Could not find mask image file: {args.mask}')

    # ACQUISITION PARAMETERS
    try:
        eddyPara = np.genfromtxt(os.path.join(args.eddydir, args.eddy_params), dtype=float)
        #eddyPara = eddyPara.flatten()
        if eddyPara.ndim > 1:
            tmp_eddyPara = np.ascontiguousarray(eddyPara).view(np.dtype((np.void, eddyPara.dtype.itemsize * eddyPara.shape[1])))
            _, idx, inv_idx = np.unique(tmp_eddyPara, return_index=True, return_inverse=True)
            eddyIdxs = inv_idx[eddyIdxs-1]+1
            eddyPara = eddyPara[idx]
        eddyPara = eddyPara.flatten()
    except Exception as exc:
        raise ValueError(f'Failed to read EDDY parameter file: {args.params}: {exc}')


    # BVECS
    bvecs = np.array([])
    if args.bvecs:
        try:
            bvecs = np.genfromtxt(args.bvecs, dtype=float)
        except Exception as exc:
            raise ValueError(f'Failed to read BVECS parameter file: {args.bvecs}: {exc}')

        if bvecs.shape[1] != bvals.size:
            raise ValueError('bvecs and bvals do not have consistent dimensions')

    # Fieldmap
    field = None
    if args.field:
        field = _imgfile(args.field)
       
    # Slspec
    slspec = None
    if args.slspec:
        try:
            slspec = np.genfromtxt(args.slspec, dtype=int)
        except Exception as exc:
            raise ValueError(f'Failed to read SLSPEC parameter file: {args.slspec}: {exc}')

    # OUTPUT FOLDER
    if not args.output:
        args.output = _eddyfile(args, ".qc")
    if os.path.exists(args.output) and not args.overwrite:
        raise ValueError(f"Output directory {args.output} already exists - remove or specify a different name")
    os.makedirs(args.output, exist_ok=True)

    # Load eddy corrected file and check for consistency between input dimensions
    eddy_epi = nib.load(eddyfile)   
    if bvals is not None and eddy_epi.shape[3] != np.max(bvals.shape):
        raise ValueError(f'Number of bvals not consistent with EDDY corrected file {eddyfile}')
    elif eddy_epi.shape[3] != np.max(eddyIdxs.shape):
        raise ValueError(f'Number of eddy indices not consistent with EDDY corrected file {eddyfile}')

    # Load binary brain mask file
    if mask:
        mask_vol = nib.load(mask)   
        if eddy_epi.shape[0:3] != mask_vol.shape:
            raise ValueError('Mask and data dimensions are not consistent')

    #=========================================================================================
    # Get data info and fill data dictionary
    #=========================================================================================
    rounded_bvals = utils.round_bvals(bvals)
    unique_bvals, counts = np.unique(rounded_bvals.astype(int), return_counts=True)
    unique_pedirs, counts_pedirs = np.unique(eddyIdxs, return_counts=True)
    protocol = np.full((unique_pedirs.size,unique_bvals.size), -1, dtype=int)
    for c_b, b in enumerate(unique_bvals):
        for c_p, p in enumerate(unique_pedirs):
            protocol[c_p, c_b] = ((rounded_bvals==b) & (eddyIdxs==p)).sum()

    data = {
        'subjid' : eddyfile,
        'file_mask': mask,
        'num_dw_vols': int((bvals > 100).sum()),
        'num_b0_vols': int((bvals <= 100).sum()),
        'protocol':protocol.flatten(),
        'num_pe_dirs': int(np.size(unique_pedirs)),
        'num_shells': int((unique_bvals > 0).sum()),
        'bvals' : bvals,
        'rounded_bvals' : rounded_bvals,
        'bvecs' : bvecs,
        'bvecs' : bvecs,
        'unique_bvals' : unique_bvals[unique_bvals > 100],
        'bvals_dirs' : counts[unique_bvals > 100],
        'eddy_idxs' : eddyIdxs,
        'eddy_para' : eddyPara,
        'unique_pedirs' : unique_pedirs,
        'counts_pedirs' : counts_pedirs,
        'shape' : eddy_epi.shape,
        'vox_sizes' : np.array(eddy_epi.header.get_zooms())[:3],
        'file_epi' : eddy_epi,
    }

    #=========================================================================================
    # Check which output files exist and compute qc stats
    #=========================================================================================
    qc_data = {}
    motionFile = _eddyfile(args, '.eddy_movement_rms')            # Text file containing no. volumes X 2 columns
    paramsFile = _eddyfile(args, '.eddy_parameters')              # Text file containing no. volumes X 9 columns
    s2vParamsFile = _eddyfile(args, '.eddy_movement_over_time')   # Text file containing (no. volumes X no.slices / MB) rows and 6 columns
    olMapFile = _eddyfile(args, '.eddy_outlier_map')              # Text file containing binary matrix [no. volumes X no. slices]
    cnrFile = _eddyfile(args, '.eddy_cnr_maps.nii.gz')            # 4D file containing the eddy-based b-CNR maps (std(pred)/std(res))
    rssFile = _eddyfile(args, '.eddy_residuals.nii.gz')           # 4D file containing the eddy-based residuals
    
    if os.path.isfile(motionFile):
        LOG.debug('RMS movement estimates file detected')
        motion = np.genfromtxt(motionFile,dtype=float)
        qc_data['motion_abs'] = motion[:, 0]
        qc_data['motion_rel'] = motion[:, 1]
        qc_data['motion_abs_mean'] = np.mean(motion[:, 0])
        qc_data['motion_rel_mean'] = np.mean(motion[:, 1])

    if os.path.isfile(paramsFile):
        LOG.debug('Eddy parameters file detected')
        params = np.genfromtxt(paramsFile, dtype=float)
        qc_data['motion_v2v_trans_mean'] = np.mean(params[:,0:3], axis=0)
        qc_data['motion_v2v_rot_mean'] = np.mean(np.rad2deg(params[:,3:6]), axis=0)
        qc_data['motion_ec_lin_std'] = np.std(params[:,6:9], axis=0)

    if os.path.isfile(s2vParamsFile):
        LOG.debug('Eddy s2v movement file detected')
        s2v_params = np.genfromtxt(s2vParamsFile, dtype=float)
        qc_data['motion_s2v_trans'] = s2v_params[:,0:3]
        qc_data['motion_s2v_rot'] = np.rad2deg(s2v_params[:,3:6])
        n_vox_thr = 240 # Minimum number of voxels in a masked slice
        if slspec is not None:
            n_ex = slspec.shape[0]
            if slspec.ndim > 1:
                ex_check = np.arange(0, n_ex)
            else:
                ex_check = np.where(np.sum(np.sum(data['file_mask'][:,:,slspec], axis=0), axis=0) > n_vox_thr)
        else:
            LOG.warn('slspec file not provided. Assuming one excitation per slice.')
            n_ex = data['shape'][2]
            ex_check = np.arange(0, n_ex)

        if n_ex * data['bvals'].size != qc_data['s2v_params'].shape[0]:
            print('Warning: number of s2v parameters does not match the expected one! Skipping s2v QC...')
            qc_data.pop('motion_s2v_trans')
            qc_data.pop('motion_s2v_rot')
        else:
            qc_data['motion_s2v_trans_var'] = np.zeros((data['bvals'].size, 3))
            qc_data['motion_s2v_rot_var'] = np.zeros((data['bvals'].size, 3))
            for i in np.arange(0, data['bvals'].size):
                tmp = s2v_params[i*n_ex:(i+1)*n_ex]
                qc_data['motion_s2v_trans_var'][i] = np.var(qc_data['motion_s2v_trans'][i*n_ex:(i+1)*n_ex][ex_check], ddof=1, axis=0)
                qc_data['motion_s2v_rot_var'][i] = np.var(qc_data['motion_s2v_rot'][i*n_ex:(i+1)*n_ex][ex_check], ddof=1, axis=0)
            qc_data['motion_s2v_trans_std_mean'] = np.sqrt(np.mean(qc_data['motion_s2v_trans_var'], axis=0))
            qc_data['motion_s2v_rot_std_mean'] = np.sqrt(np.mean(qc_data['motion_s2v_rot_var'], axis=0))
            
    if os.path.isfile(olMapFile):
        LOG.debug('Outliers outuput files detected')
        ol_map = np.genfromtxt(olMapFile,dtype=None, delimiter=" ", skip_header=1)
        ol_map_std = np.genfromtxt(_eddyfile(args, '.eddy_outlier_n_stdev_map'), dtype=float, delimiter=" ", skip_header=1)
        qc_data['outliers_tot'] = 100*np.count_nonzero(ol_map)/(data['num_dw_vols']*data['shape'][2])
        qc_data['outliers_tot_bval'] = np.full(data['unique_bvals'].size, -1.0)
        qc_data['outliers_tot_pe'] = np.full(data['num_pe_dirs'], -1.0)
        for i in range(0, data['unique_bvals'].size):
            qc_data['outliers_tot_bval'][i] = 100*np.count_nonzero(ol_map[data['bvals'] == data['unique_bvals'][i], :])/(data['bvals_dirs'][i]*data['shape'][2])
        for i in range(0, data['num_pe_dirs']):
            qc_data['outliers_tot_pe'][i] = 100*np.count_nonzero(ol_map[data['eddy_idxs'] == data['unique_pedirs'][i],:])/(data['counts_pedirs'][i]*data['shape'][2])
        
    if os.path.isfile(cnrFile):
        LOG.debug('CNR output files detected')
        cnrImg = nib.load(cnrFile)
        cnr = cnrImg.get_data()
        if np.count_nonzero(np.isnan(cnr)):
            LOG.warn("NaNs detected in the CNR maps")
        finiteMask = (data['file_mask'] != 0) * np.isfinite(cnr[:,:,:,0])
        qc_data['cnr_mean_bval'] = np.full(1+data['unique_bvals'].size, -1.0)
        qc_data['cnr_std_bval'] = np.full(1+data['unique_bvals'].size, -1.0)
        qc_data['cnr_mean_bval'][0] = round(np.nanmean(cnr[:,:,:,0][finiteMask]), 2)
        qc_data['cnr_std_bval'][0] = round(np.nanstd(cnr[:,:,:,0][finiteMask]), 2)
        for i in range(0,data['unique_bvals'].size):
            finiteMask = (data['file_mask'] != 0) * np.isfinite(cnr[:,:,:,i+1])
            qc_data['cnr_mean_bval'][i+1] = round(np.nanmean(cnr[:,:,:,i+1][finiteMask]), 2)
            qc_data['cnr_std_bval'][i+1] = round(np.nanstd(cnr[:,:,:,i+1][finiteMask]), 2)

    if os.path.isfile(rssFile):
        LOG.debug('Eddy residuals file detected')
        rssImg = nib.load(rssFile)
        rss = rssImg.get_data()
        qc_data['res_mean'] = np.full(data['bvals'].size, -1.0),
        for i in range(0,data['bvals'].size):
            qc_data['res_mean'][i] = np.mean(np.power(rss[:,:,:,i][data['file_mask'] != 0.0], 2))
        rssImg.uncache()
        del rss
        # FIXME
        # np.savetxt(data['path'] + '/eddy_msr.txt', np.reshape(qc_data['avg_rss'], (1,-1)), fmt='%f', delimiter=' ')
    
    if field is not None:
        if not os.path.isfile(field):
            raise ValueError(f"No such file: {field}")
        LOG.debug('Topup fieldmap file detected')
        fieldImg = nib.load(field)
        fieldMap = fieldImg.get_data()
        dispField = fieldMap*eddyPara[3]
        qc_data['field_disp_std'] = np.std(dispField[data['file_mask'] != 0.0])
        fieldImg.uncache()
        del fieldMap

    # Stop if motion or parameters estimates are missing FIXME
    #if (eddyOutput['motionFlag'] == False or
    #    eddyOutput['paramsFlag'] == False):
    #    raise ValueError('Motion estimates and/or eddy estimated parameters are missing!')

    full_data = {}
    data.pop("file_epi")
    for k, v in data.items():
        if isinstance(v, np.ndarray):
            full_data['data_' + k] = v.tolist()
        else:
            full_data['data_' + k] = v
    for k, v in qc_data.items():
        if isinstance(v, np.ndarray):
            full_data['qc_' + k] = v.tolist()
        else:
            full_data['qc_' + k] = v

    # Export stats and data info to json file
    with open(os.path.join(args.output, 'qc.json'), 'w') as fp:
        json.dump(full_data, fp, sort_keys=True, indent=4, separators=(',', ': '))