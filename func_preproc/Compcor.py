def compcor_workflow(SinkTag="func_preproc", wf_name="compcor"):
    """


               `source: -`


               Component based noise reduction method (Behzadi et al.,2007): Regressing out principal components from noise ROIs.
               Here the aCompCor is used.

               Workflow inputs:
                   :param func_aligned: The reoriented and realigned functional image.
                   :param mask_files: Mask files which determine ROI(s). The default mask is the
                   :param components_file
                   :param num_componenets:
                   :param pre_filter: Detrend time series prior to component extraction.
                   :param TR
                   :param SinkDir:
                   :param SinkTag: The output directory in which the returned images (see workflow outputs) could be found in a subdirectory directory specific for this workflow.

               Workflow outputs:




                   :return: slt_workflow - workflow




               Balint Kincses
               kincses.balint@med.u-szeged.hu
               2018


     """





    import os
    import nipype
    import nipype.pipeline as pe
    import nipype.algorithms.confounds as cnf
    import PUMI.func_preproc.info.info_get as info_get
    import PUMI.utils.utils_convert as utils_convert
    import nipype.interfaces.io as io
    import nipype.interfaces.utility as utility
    import nipype.interfaces.fsl as fsl
    import PUMI.utils.QC as qc
    import PUMI.utils.globals as globals

    SinkDir = os.path.abspath(globals._SinkDir_ + "/" + SinkTag)
    if not os.path.exists(SinkDir):
        os.makedirs(SinkDir)

    # Basic interface class generates identity mappings
    inputspec = pe.Node(utility.IdentityInterface(fields=['func_aligned',
                                                          'mask_file']),
                        name='inputspec')

    myqc = qc.vol2png("compcor_noiseroi")

    # Save outputs which are important
    ds_nii = pe.Node(interface=io.DataSink(),
                 name='ds_nii')
    ds_nii.inputs.base_directory = SinkDir
    ds_nii.inputs.regexp_substitutions = [("(\/)[^\/]*$", ".nii.gz")]

    # standardize timeseries prior to compcor. added by tspisak
    scale = pe.MapNode(interface=utility.Function(input_names=['in_file'],
                                                  output_names=['scaled_file'],
                                                  function=scale_vol),
                       iterfield=['in_file'],
                       name='scale_func')

    # Calculate compcor files
    compcor=pe.MapNode(interface=cnf.ACompCor(pre_filter='polynomial',header_prefix="",num_components=5),
                       iterfield=['realigned_file','repetition_time','mask_files'],
                    name='compcor')

    # Custom interface wrapping function Float2Str
    func_str2float = pe.MapNode(interface=utils_convert.Str2Float,
                                iterfield=['str'],
                               name='func_str2float')
    # Drop first line of the Acompcor function output
    drop_firstline=pe.MapNode(interface=utils_convert.DropFirstLine,
               iterfield=['txt'],
               name='drop_firstline'
                )
    # Custom interface wrapping function TR
    TRvalue = pe.MapNode(interface=info_get.TR,
                         iterfield=['in_file'],
                      name='TRvalue')

    # Basic interface class generates identity mappings
    outputspec = pe.Node(utility.IdentityInterface(fields=['components_file']),
                         name='outputspec')

    # save data out with Datasink
    ds_text = pe.Node(interface=io.DataSink(), name='ds_txt')
    ds_text.inputs.regexp_substitutions = [("(\/)[^\/]*$", ".txt")]
    ds_text.inputs.base_directory = SinkDir

    # Create a workflow to connect all those nodes
    analysisflow = nipype.Workflow(wf_name)
    analysisflow.connect(inputspec, 'func_aligned', scale, 'in_file')
    analysisflow.connect(scale, 'scaled_file', compcor, 'realigned_file')
    analysisflow.connect(inputspec, 'func_aligned', TRvalue, 'in_file')
    analysisflow.connect(TRvalue, 'TR', func_str2float, 'str')
    analysisflow.connect(func_str2float, 'float', compcor, 'repetition_time')
    #analysisflow.connect(TRvalue, 'TR', compcor, 'repetition_time')
    analysisflow.connect(inputspec, 'mask_file', compcor, 'mask_files')
    analysisflow.connect(compcor, 'components_file',drop_firstline,'txt')
    analysisflow.connect(drop_firstline, 'droppedtxtfloat', outputspec, 'components_file')
    analysisflow.connect(compcor, 'components_file', ds_text, 'compcor_noise')

    analysisflow.connect(inputspec, 'func_aligned', myqc, 'inputspec.bg_image')
    analysisflow.connect(inputspec, 'mask_file', myqc, 'inputspec.overlay_image')

    analysisflow.connect(inputspec, 'mask_file', ds_nii, 'compcor_noise_mask')

    return analysisflow

def create_anat_noise_roi_workflow(SinkTag="func_preproc", wf_name="create_noise_roi"):
    """
    Creates an anatomical noise ROI for use with compcor

    inputs are awaited from the (BBR-based) func2anat registration
    and are already transformed to functional space

    Tamas Spisak
    2018


    """
    import os
    import nipype
    import nipype.pipeline as pe
    import nipype.interfaces.utility as utility
    import nipype.interfaces.fsl as fsl
    import PUMI.utils.globals as globals

    # Basic interface class generates identity mappings
    inputspec = pe.Node(utility.IdentityInterface(fields=['wm_mask',
                                                          'ventricle_mask']),
                        name='inputspec')

    # Basic interface class generates identity mappings
    outputspec = pe.Node(utility.IdentityInterface(fields=['noise_roi']),
                        name='outputspec')

    SinkDir = os.path.abspath(globals._SinkDir_ + "/" + SinkTag)
    if not os.path.exists(SinkDir):
        os.makedirs(SinkDir)
    wf = nipype.Workflow(wf_name)

    # erode WM mask in functional space
    erode_mask = pe.MapNode(fsl.ErodeImage(),
                            iterfield=['in_file'],
                            name="erode_wm_mask")
    wf.connect(inputspec, 'wm_mask', erode_mask, 'in_file')

    # add ventricle and eroded WM masks
    add_masks = pe.MapNode(fsl.ImageMaths(op_string=' -add'),
                           iterfield=['in_file', 'in_file2'],
                           name="addimgs")

    wf.connect(inputspec, 'ventricle_mask', add_masks, 'in_file')
    wf.connect(erode_mask, 'out_file', add_masks, 'in_file2')

    wf.connect(add_masks, 'out_file', outputspec, 'noise_roi')

    return wf


def scale_vol(in_file):
    import nibabel as nb
    import numpy as np
    import os
    img=nb.load(in_file)
    DATA=img.get_data()
    STD=np.std(DATA, axis=3)
    STD[STD == 0] = 1  # divide with 1
    MEAN=np.mean(DATA, axis=3)

    for i in range(DATA.shape[3]):
        DATA[:,:,:,i] = (DATA[:,:,:,i]-MEAN)/STD

    ret = nb.Nifti1Image(DATA, img.affine, img.header)
    out_file = "scaled_func.nii.gz"
    nb.save(ret, out_file)
    return os.path.join(os.getcwd(), out_file)