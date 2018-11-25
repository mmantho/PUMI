#!/usr/bin/env python
# This is a pipeline doing resting-state fMRI preprocessing as done in the PAINTeR study
# https://github.com/spisakt/PAINTeR
#
# The pipeline performs:
# - a standard anatomical image processing (AnatProc) with:
#   - brain extraction with FSL bet
#   - FSL FAST tissue segmentation
#   - ANTs-based standardisation
#   - etc.
# - BBR-based func2anat registration
# - preprocessing of functional images with (FuncProc_despike_afni):
#   - brain extraction
#   - FSL McFlirt motion correction
#   - despiking with AFNI
#   - temporal filtering (default band: 0.008-0.08)
#   - a "liberal" scrubbing (since despiking has done much of the work already...)
# - picks brain atlas, reorders labels by modules
# - transforms atlas into the native space, masks it with native GM mask and generates regional timeseries
# - computes partial correlation matrix based on the normalised regional timeseries

# - computing the pain sensitivity score from the matrix is not included here and can be found in
# https://github.com/spisakt/PAINTeR
import warnings
warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")

import sys
# sys.path.append("/home/balint/Dokumentumok/phd/github/") #PUMI should be added to the path by install or by the developer
# az importalasnal az ~_preproc utan a .fajlnev-et kell megadni
import nipype
import nipype.pipeline as pe
# import the defined workflows from the anat_preproc folder
import nipype.interfaces.io as io
import nipype.interfaces.fsl as fsl
import nipype.interfaces.afni as afni
import nipype.interfaces.utility as utility
import PUMI.AnatProc as anatproc
import PUMI.FuncProc as funcproc
import PUMI.func_preproc.Compcor as cc
# import the necessary workflows from the func_preproc folder
import PUMI.anat_preproc.Func2Anat as bbr
import PUMI.func_preproc.func2standard as transform
import PUMI.utils.utils_convert as utils_convert
import os
import PUMI.utils.globals as globals
import PUMI.connectivity.TimeseriesExtractor as tsext
import nipype.interfaces.nilearn as learn
import PUMI.utils.QC as qc
import PUMI.connectivity.NetworkBuilder as nw


# parse command line arguments
if (len(sys.argv) <= 2):
    print("Please specify command line arguments!")
    print("Usage:")
    print(sys.argv[0] + " <\"highres_data_template\"> <\"func_data_template\"> [results_sink_directory]")
    print("Example:")
    print(sys.argv[0] + " \"highres_data/subject_*.nii.gz\" \"func_data/subject_*.nii.gz\"")
    quit()

if (len(sys.argv) > 3):
    globals._SinkDir_ = sys.argv[3]

if (len(sys.argv) > 4):
    _MISTDIR_=sys.argv[4]
else:
    _MISTDIR_ = '/home/analyser/Documents/mistatlases/'

##############################
globals._brainref="/data/standard/MNI152_T1_2mm_brain.nii.gz"
globals._headref="/data/standard/MNI152_T1_2mm.nii.gz"
globals._brainref_mask="/data/standard/MNI152_T1_2mm_brain_mask_dil.nii.gz"
##############################
_refvolplace_ = globals._RefVolPos_.first


# specify atlas for network construction:
# name of labelmap nii (or list of probmaps)
_ATLAS_FILE = _MISTDIR_ + '/Parcellations/MIST_122.nii.gz'
# a list of labels, where index+1 corresponds to the label in the labelmap
_ATLAS_LABELS = tsext.mist_labels(mist_directory=_MISTDIR_, resolution="122")
# a list of labels, where index i corresponds to the module of the i+1th region, this is optional
_ATLAS_MODULES = tsext.mist_modules(mist_directory=_MISTDIR_, resolution="122")
##############################
##############################
#_regtype_ = globals._RegType_.FSL
globals._regType_ = globals._RegType_.ANTS
##############################

totalWorkflow = nipype.Workflow('comp')
totalWorkflow.base_dir = '.'

# create data grabber
datagrab = pe.Node(io.DataGrabber(outfields=['func', 'struct']), name='data_grabber')

datagrab.inputs.base_directory = os.getcwd()  # do we need this?
datagrab.inputs.template = "*"  # do we need this?
datagrab.inputs.field_template = dict(func=sys.argv[2],
                                      struct=sys.argv[1])  # specified by command line arguments
datagrab.inputs.sort_filelist = True

# sink: file - idx relationship!!
pop_id = pe.Node(interface=utils_convert.List2TxtFile,
                     name='pop_id')
pop_id.inputs.rownum = 0
pop_id.inputs.out_file = "subject_IDs.txt"
totalWorkflow.connect(datagrab, 'func', pop_id, 'in_list')

ds_id = pe.Node(interface=io.DataSink(), name='ds_pop_id')
ds_id.inputs.regexp_substitutions = [("(\/)[^\/]*$", "IDs.txt")]
ds_id.inputs.base_directory = globals._SinkDir_
totalWorkflow.connect(pop_id, 'txt_file', ds_id, 'subjects')

# build the actual pipeline
reorient_struct = pe.MapNode(fsl.utils.Reorient2Std(),
                      iterfield=['in_file'],
                      name="reorient_struct")
totalWorkflow.connect(datagrab, 'struct', reorient_struct, 'in_file')

reorient_func = pe.MapNode(fsl.utils.Reorient2Std(),
                      iterfield=['in_file'],
                      name="reorient_func")
totalWorkflow.connect(datagrab, 'func', reorient_func, 'in_file')

myanatproc = anatproc.AnatProc(stdreg=globals._regType_)
myanatproc.inputs.inputspec.bet_fract_int_thr = 0.3  # feel free to adjust, a nice bet is important!
myanatproc.inputs.inputspec.bet_vertical_gradient = -0.3 # feel free to adjust, a nice bet is important!
# try scripts/opt_bet.py to optimise these parameters
totalWorkflow.connect(reorient_struct, 'out_file', myanatproc, 'inputspec.anat')

mybbr = bbr.bbr_workflow()
totalWorkflow.connect(reorient_struct, 'out_file', mybbr, 'inputspec.skull')
totalWorkflow.connect(reorient_func, 'out_file', mybbr, 'inputspec.func')
totalWorkflow.connect(myanatproc, 'outputspec.probmap_wm', mybbr, 'inputspec.anat_wm_segmentation')
totalWorkflow.connect(myanatproc, 'outputspec.probmap_csf', mybbr, 'inputspec.anat_csf_segmentation')
totalWorkflow.connect(myanatproc, 'outputspec.probmap_gm', mybbr, 'inputspec.anat_gm_segmentation')
totalWorkflow.connect(myanatproc, 'outputspec.probmap_ventricle', mybbr, 'inputspec.anat_ventricle_segmentation')

# Add arbitrary number of nii images wthin the same space. The default is to add csf and wm masks for anatcompcor calculation.
#myadding=adding.addimgs_workflow(numimgs=2)

# ToDo_ready: put compcor-related mask handling into a nested pipeline
# TODO_ready: erode compcor noise mask!!!!
# NOTE: more CSF voxels are retained for compcor when only WM signal is eroded and csf is added to it

compcor_roi = cc.create_anat_noise_roi_workflow()
totalWorkflow.connect(mybbr, 'outputspec.wm_mask_in_funcspace', compcor_roi, 'inputspec.wm_mask')
totalWorkflow.connect(mybbr, 'outputspec.ventricle_mask_in_funcspace', compcor_roi, 'inputspec.ventricle_mask')

# Preprocessing of functional data
myfuncproc = funcproc.FuncProc_despike_afni(carpet_plot="carpet_plots")
totalWorkflow.connect(reorient_func, 'out_file', myfuncproc, 'inputspec.func')
totalWorkflow.connect(compcor_roi, 'outputspec.noise_roi', myfuncproc, 'inputspec.cc_noise_roi')

# Pick atlas
pickatlas = tsext.PickAtlas()
pickatlas.inputs.inputspec.labelmap = _MISTDIR_ + "/Parcellations/MIST_122.nii.gz"
pickatlas.inputs.inputspec.modules = _ATLAS_MODULES
pickatlas.inputs.inputspec.labels = _ATLAS_LABELS

# Extract timeseries
extract_timeseries = tsext.extract_timeseries_nativespace()
totalWorkflow.connect(pickatlas, 'outputspec.relabeled_atlas', extract_timeseries, 'inputspec.atlas')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_labels', extract_timeseries, 'inputspec.labels')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_modules', extract_timeseries, 'inputspec.modules')
totalWorkflow.connect(myanatproc, 'outputspec.brain', extract_timeseries, 'inputspec.anat')
totalWorkflow.connect(mybbr, 'outputspec.anat_to_func_linear_xfm', extract_timeseries, 'inputspec.inv_linear_reg_mtrx')
totalWorkflow.connect(myanatproc, 'outputspec.mni2anat_warpfield', extract_timeseries, 'inputspec.inv_nonlinear_reg_mtrx')
totalWorkflow.connect(mybbr, 'outputspec.gm_mask_in_funcspace', extract_timeseries, 'inputspec.gm_mask')
totalWorkflow.connect(myfuncproc, 'outputspec.func_preprocessed', extract_timeseries, 'inputspec.func')
totalWorkflow.connect(myfuncproc, 'outputspec.FD', extract_timeseries, 'inputspec.confounds')


# compute connectivity
measure = "partial correlation"
mynetmat = nw.build_netmat(wf_name=measure.replace(" ", "_"))
mynetmat.inputs.inputspec.measure = measure

totalWorkflow.connect(extract_timeseries, 'outputspec.timeseries', mynetmat, 'inputspec.timeseries')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_modules', mynetmat, 'inputspec.modules')
totalWorkflow.connect(pickatlas, 'outputspec.relabeled_atlas', mynetmat, 'inputspec.atlas')

# Extract timeseries
extract_timeseries_scrubbed = tsext.extract_timeseries_nativespace(SinkTag="connectivity_scrubbed", wf_name="extract_timeseries_nativespace_scribbed")
totalWorkflow.connect(pickatlas, 'outputspec.relabeled_atlas', extract_timeseries_scrubbed, 'inputspec.atlas')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_labels', extract_timeseries_scrubbed, 'inputspec.labels')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_modules', extract_timeseries_scrubbed, 'inputspec.modules')
totalWorkflow.connect(myanatproc, 'outputspec.brain', extract_timeseries_scrubbed, 'inputspec.anat')
totalWorkflow.connect(mybbr, 'outputspec.anat_to_func_linear_xfm', extract_timeseries_scrubbed, 'inputspec.inv_linear_reg_mtrx')
totalWorkflow.connect(myanatproc, 'outputspec.mni2anat_warpfield', extract_timeseries_scrubbed, 'inputspec.inv_nonlinear_reg_mtrx')
totalWorkflow.connect(mybbr, 'outputspec.gm_mask_in_funcspace', extract_timeseries_scrubbed, 'inputspec.gm_mask')
totalWorkflow.connect(myfuncproc, 'outputspec.func_preprocessed_scrubbed', extract_timeseries_scrubbed, 'inputspec.func')
totalWorkflow.connect(myfuncproc, 'outputspec.FD', extract_timeseries_scrubbed, 'inputspec.confounds')


# compute connectivity
measure = "partial correlation"
mynetmat_scrubbed = nw.build_netmat(SinkTag="connectivity_scrubbed", wf_name=measure.replace(" ", "_") + "_scrubbed")
mynetmat_scrubbed.inputs.inputspec.measure = measure

totalWorkflow.connect(extract_timeseries_scrubbed, 'outputspec.timeseries', mynetmat_scrubbed, 'inputspec.timeseries')
totalWorkflow.connect(pickatlas, 'outputspec.reordered_modules', mynetmat_scrubbed, 'inputspec.modules')
totalWorkflow.connect(pickatlas, 'outputspec.relabeled_atlas', mynetmat_scrubbed, 'inputspec.atlas')

"""
#ToDo_ready: include scrubbing into FuncProc_despike_afni()???
myscrub = scrub.datacens_workflow_threshold()

#Todo: PickAtlas Node with reorder=True (with modulers given)

#########################
atlasinput=pe.Node(utility.IdentityInterface(fields=['modules', 'labels', 'labelmap']),
                   name="atlasinput")
atlasinput.inputs.modules = _ATLAS_MODULES
atlasinput.inputs.labels = _ATLAS_LABELS
atlasinput.inputs.labelmap=_MISTDIR_ + "/Parcellations/MIST_122.nii.gz"

relabel_atls = pe.Node(interface=utility.Function(input_names=['atlas_file', 'modules', 'labels'],
                       output_names=['relabelled_atlas_file', 'reordered_modules', 'reordered_labels', 'newlabels_file'],
                       function=tsext.relabel_atlas),
                                name='relabel_atlas2')

#create atlas matching the stabndard space used
resample_atlas = pe.Node(interface=afni.Resample(outputtype='NIFTI_GZ',
                                          master=globals._FSLDIR_ + globals._brainref),
                         name='resample_atlas') #default interpolation is nearest neighbour

resample_atlas_3mm = pe.Node(interface=afni.Resample(outputtype='NIFTI_GZ', # only for the carpet plot
                                          master=globals._FSLDIR_ + "/data/standard/MNI152_T1_3mm_brain.nii.gz"),
                         name='resample_atlas_3mm') #default interpolation is nearest neighbour

# Save outputs which are important
ds_nii = pe.Node(interface=io.DataSink(),
                         name='ds_relabeled_atlas')
ds_nii.inputs.base_directory = globals._SinkDir_
ds_nii.inputs.regexp_substitutions = [("(\/)[^\/]*$", ".nii.gz")]

        # Save outputs which are important
ds_newlabels = pe.Node(interface=io.DataSink(),
                         name='ds_newlabels')
ds_newlabels.inputs.base_directory = globals._SinkDir_
ds_newlabels.inputs.regexp_substitutions = [("(\/)[^\/]*$", ".tsv")]

#ToDo: extract regional timeseries by transforming to native space (mask with GM=True)

# transform atlas back to native EPI spaces!
atlas2native = transform.atlas2func(stdreg=_regtype_)

#extract_timesereies = pe.MapNode(interface=learn.SignalExtraction(detrend=False, include_global=False),
#                                 iterfield=['in_file', 'label_files'],
#                                 name='extract_timeseries')

extract_timesereies = pe.MapNode(interface=utility.Function(input_names=['labels', 'labelmap', 'func', 'mask'],
                                                            output_names=['out_file', 'labels', 'out_gm_label'],
                                                            function=tsext.TsExtractor),
                                 iterfield=['labelmap', 'func', 'mask'],
                                 name='extract_timeseries')

extract_timesereies_scrub = pe.MapNode(interface=utility.Function(input_names=['labels', 'labelmap', 'func', 'mask'],
                                                            output_names=['out_file', 'labels', 'out_gm_label'],
                                                            function=tsext.TsExtractor),
                                 iterfield=['labelmap', 'func', 'mask'],
                                 name='extract_timeseries_scrub')



# Save outputs which are important
ds_txt = pe.Node(interface=io.DataSink(),
                 name='ds_txt')
ds_txt.inputs.base_directory = globals._SinkDir_
ds_txt.inputs.regexp_substitutions = [("(\/)[^\/]*$", "timeseries" + ".tsv")]

#QC
timeseries_qc = qc.regTimeseriesQC("regional_timeseries", tag="timeseries")

#ToDo: calculate connectivity matrix (default: partial correlation)

measure = "tangent"
mynetmat = nw.build_netmat(wf_name=measure.replace(" ", "_"))
mynetmat.inputs.inputspec.measure = measure
"""

"""
totalWorkflow.connect(extract_timesereies, 'out_file', mynetmat, 'inputspec.timeseries')
totalWorkflow.connect(relabel_atls, 'reordered_modules', mynetmat, 'inputspec.modules')
totalWorkflow.connect(resample_atlas_3mm, 'out_file', mynetmat, 'inputspec.atlas')

totalWorkflow.connect(atlasinput, 'modules', relabel_atls, 'modules')
totalWorkflow.connect(atlasinput, 'labels', relabel_atls, 'labels')
totalWorkflow.connect(atlasinput, 'labelmap', relabel_atls, 'atlas_file')
totalWorkflow.connect(relabel_atls, 'relabelled_atlas_file', resample_atlas, 'in_file')
totalWorkflow.connect(relabel_atls, 'relabelled_atlas_file', resample_atlas_3mm, 'in_file')
totalWorkflow.connect(resample_atlas, 'out_file', atlas2native, 'inputspec.atlas')

totalWorkflow.connect(atlas2native, 'outputspec.atlas2func', extract_timesereies, 'labelmap')
totalWorkflow.connect(mybbr, 'outputspec.gm_mask_in_funcspace', extract_timesereies, 'mask')
totalWorkflow.connect(relabel_atls, 'reordered_labels', extract_timesereies, 'labels')
totalWorkflow.connect(myfuncproc, 'outputspec.func_preprocessed', extract_timesereies, 'func')

totalWorkflow.connect(atlas2native, 'outputspec.atlas2func', extract_timesereies_scrub, 'labelmap')
totalWorkflow.connect(mybbr, 'outputspec.gm_mask_in_funcspace', extract_timesereies_scrub, 'mask')
totalWorkflow.connect(relabel_atls, 'reordered_labels', extract_timesereies_scrub, 'labels')
totalWorkflow.connect(myscrub, 'outputspec.scrubbed_image', extract_timesereies_scrub, 'func')

totalWorkflow.connect(myfuncproc, 'outputspec.func_preprocessed', myscrub, 'inputspec.func')
totalWorkflow.connect(myfuncproc, 'outputspec.FD', myscrub, 'inputspec.FD')




totalWorkflow.connect(relabel_atls, 'reordered_modules', timeseries_qc, 'inputspec.modules')
totalWorkflow.connect(resample_atlas_3mm, 'out_file', timeseries_qc, 'inputspec.atlas')
totalWorkflow.connect(resample_atlas, 'out_file', ds_nii, 'atlas_relabeled')
totalWorkflow.connect(relabel_atls, 'newlabels_file', ds_newlabels, 'atlas_relabeled')
totalWorkflow.connect(extract_timesereies, 'out_file', ds_txt, 'regional_timeseries')
totalWorkflow.connect(extract_timesereies, 'out_file', timeseries_qc, 'inputspec.timeseries')
totalWorkflow.connect(extract_timesereies, 'out_gm_label', ds_nii, 'gm_label_funcspace')

totalWorkflow.connect(extract_timesereies_scrub, 'out_file', ds_txt, 'regional_timeseries_scrub')
"""
##################

# standardize what you need
#myfunc2mni = transform.func2mni(stdreg=_regtype_, carpet_plot="1_original", wf_name="func2mni_1")
#myfunc2mni_nuis = transform.func2mni(stdreg=_regtype_, carpet_plot="2_nuis", wf_name="func2mni_2_nuis")
#myfunc2mni_nuis_medang = transform.func2mni(stdreg=_regtype_, carpet_plot="3_nuis_medang", wf_name="func2mni_3_nuis_medang")
#myfunc2mni_nuis_medang_bpf = transform.func2mni(stdreg=_regtype_, carpet_plot="5_nuis_medang_bptf", wf_name="func2mni_4_nuis_medang_bptf")

###################


# connect network analysis part
#totalWorkflow.connect(atlas2native, 'outputspec.func_std', myextract, 'inputspec.std_func')
#totalWorkflow.connect(myextract, 'outputspec.timeseries_file', mynetmat, 'inputspec.timeseries')
#totalWorkflow.connect(myextract, 'outputspec.reordered_modules', mynetmat, 'inputspec.modules')
#totalWorkflow.connect(myextract, 'outputspec.relabelled_atlas_file', mynetmat, 'inputspec.atlas')

totalWorkflow.write_graph('graph-orig.dot', graph2use='orig', simple_form=True)
totalWorkflow.write_graph('graph-exec-detailed.dot', graph2use='exec', simple_form=False)
totalWorkflow.write_graph('graph.dot', graph2use='colored')

from nipype.utils.profiler import log_nodes_cb
import logging
callback_log_path = 'run_stats.log'
logger = logging.getLogger('callback')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(callback_log_path)
logger.addHandler(handler)

plugin_args = {'n_procs' : 8,
               'memory_gb' : 13,
#               'status_callback' : log_nodes_cb
               }
totalWorkflow.run(plugin='MultiProc', plugin_args=plugin_args)
