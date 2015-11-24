import yaml
import argparse
import numpy as NP 
import astropy
from astropy.io import fits
from astropy.io import ascii
import progressbar as PGB
import matplotlib.pyplot as PLT
import matplotlib.colors as PLTC
import aipy as AP
import interferometry as RI
import delay_spectrum as DS
import my_DSP_modules as DSP 
import baseline_delay_horizon as DLY
import geometry as GEOM
import CLEAN_wrapper as CLN
import ipdb as PDB

## Parse input arguments

parser = argparse.ArgumentParser(description='Program to simulate interferometer array data')

input_group = parser.add_argument_group('Input parameters', 'Input specifications')
input_group.add_argument('-i', '--infile', dest='infile', default='/home/t_nithyanandan/codes/mine/python/interferometry/main/simparameters.yaml', type=file, required=False, help='File specifying input parameters')

args = vars(parser.parse_args())

with args['infile'] as parms_file:
    parms = yaml.safe_load(parms_file)

rootdir = parms['directory']['rootdir']
project = parms['project']
telescope_id = parms['telescope']['id']
pfb_method = parms['telescope']['pfb_method']
element_shape = parms['antenna']['shape']
element_size = parms['antenna']['size']
ground_plane = parms['antenna']['ground_plane']
phased_array = parms['antenna']['phased_array']
delayerr = parms['phasedarray']['delayerr']
gainerr = parms['phasedarray']['gainerr']
nrand = parms['phasedarray']['nrand']
antenna_file = parms['array']['file']
array_layout = parms['array']['layout']
minR = parms['array']['minR']
maxR = parms['array']['maxR']
minbl = parms['baseline']['min']
maxbl = parms['baseline']['max']
beam_info = parms['beam']
use_external_beam = beam_info['use_external']
if use_external_beam:
    external_beam_file = beam_info['file']
    beam_pol = beam_info['pol']
beam_chromaticity = beam_info['chromatic']
baseline_chunk_size = parms['processing']['bl_chunk_size']
n_bl_chunks = parms['processing']['n_bl_chunks']
frequency_chunk_size = parms['processing']['freq_chunk_size']
n_freq_chunks = parms['processing']['n_freq_chunks']
fg_str = parms['fgparm']['model']
nside = parms['fgparm']['nside']
Tsys = parms['telescope']['Tsys']
freq = parms['obsparm']['freq']
freq_resolution = parms['obsparm']['freq_resolution']
obs_mode = parms['obsparm']['obs_mode']
nchan = parms['obsparm']['nchan']
n_acc = parms['obsparm']['n_acc']
t_acc = parms['obsparm']['t_acc']
t_obs = parms['obsparm']['t_obs']
n_sky_sectors = parms['processing']['n_sky_sectors']
bpass_shape = parms['processing']['bpass_shape']
max_abs_delay = parms['processing']['max_abs_delay']
f_pad = parms['processing']['f_pad']
avg_drifts = parms['snapshot']['avg_drifts']
beam_switch = parms['snapshot']['beam_switch']
all_snapshots = parms['snapshot']['all']
snapshots_range = parms['snapshot']['range']
pc = parms['phasing']['center']
pc_coords = parms['phasing']['coords']
spindex_rms = parms['fgparm']['spindex_rms']
spindex_seed = parms['fgparm']['spindex_seed']

if project not in ['project_MWA', 'project_global_EoR', 'project_HERA', 'project_drift_scan', 'project_beams', 'project_LSTbin']:
    raise ValueError('Invalid project specified')
else:
    project_dir = project + '/'

if telescope_id not in ['mwa', 'vla', 'gmrt', 'hera', 'mwa_dipole', 'custom', 'paper_dipole', 'mwa_tools']:
    raise ValueError('Invalid telescope specified')

if element_shape is None:
    element_shape = 'delta'
elif element_shape not in ['dish', 'delta', 'dipole']:
    raise ValueError('Invalid antenna element shape specified')

if element_shape != 'delta':
    if element_size is None:
        raise ValueError('No antenna element size specified')
    elif element_size <= 0.0:
        raise ValueError('Antenna element size must be positive')

if not isinstance(phased_array, bool):
    raise TypeError('phased_array specification must be boolean')

if delayerr is None:
    delayerr_str = ''
    delayerr = 0.0
elif delayerr < 0.0:
    raise ValueError('delayerr must be non-negative.')
else:
    delayerr_str = 'derr_{0:.3f}ns'.format(delayerr)
delayerr *= 1e-9

if gainerr is None:
    gainerr_str = ''
    gainerr = 0.0
elif gainerr < 0.0:
    raise ValueError('gainerr must be non-negative.')
else:
    gainerr_str = '_gerr_{0:.2f}dB'.format(gainerr)

if nrand is None:
    nrandom_str = ''
    nrand = 1
elif nrand < 1:
    raise ValueError('nrandom must be positive')
else:
    nrandom_str = '_nrand_{0:0d}_'.format(nrand)

if (delayerr_str == '') and (gainerr_str == ''):
    nrand = 1
    nrandom_str = ''

delaygain_err_str = delayerr_str + gainerr_str + nrandom_str

use_GSM = False
use_DSM = False
use_CSM = False
use_SUMSS = False
use_GLEAM = False
use_USM = False
use_MSS = False
use_PS = False
use_NVSS = False
use_HI_monopole = False
use_HI_cube = False
use_HI_fluctuations = False

if fg_str not in ['asm', 'dsm', 'csm', 'nvss', 'sumss', 'gleam', 'mwacs', 'ps', 'point', 'usm', 'mss', 'HI_cube', 'HI_monopole', 'HI_fluctuations']:
    raise ValueError('Invalid foreground model string specified.')

if fg_str == 'asm':
    use_GSM = True
elif fg_str == 'dsm':
    use_DSM = True
elif fg_str == 'csm':
    use_CSM = True
elif fg_str == 'sumss':
    use_SUMSS = True
elif fg_str == 'gleam':
    use_GLEAM = True
elif fg_str in ['point', 'PS']:
    use_PS = True
elif fg_str == 'nvss':
    use_NVSS = True
elif fg_str == 'usm':
    use_USM = True
elif fg_str == 'HI_monopole':
    use_HI_monopole = True
elif fg_str == 'HI_fluctuations':
    use_HI_fluctuations = True
elif fg_str == 'HI_cube':
    use_HI_cube = True
else:
    fg_str = 'other'

if (telescope_id == 'mwa') or (telescope_id == 'mwa_dipole'):
    element_size = 0.74
    element_shape = 'dipole'
    if telescope_id == 'mwa': phased_array = True
elif telescope_id == 'vla':
    element_size = 25.0
    element_shape = 'dish'
elif telescope_id == 'gmrt':
    element_size = 45.0
    element_shape = 'dish'
elif telescope_id == 'hera':
    element_size = 14.0
    element_shape = 'dish'
elif telescope_id == 'custom':
    if element_shape != 'delta':
        if (element_shape is None) or (element_size is None):
            raise ValueError('Both antenna element shape and size must be specified for the custom telescope type.')
        elif element_size <= 0.0:
            raise ValueError('Antenna element size must be positive.')
elif telescope_id == 'mwa_tools':
    pass
else:
    raise ValueError('telescope ID must be specified.')

if telescope_id == 'custom':
    if element_shape == 'delta':
        telescope_id = 'delta'
    else:
        telescope_id = '{0:.1f}m_{1:}'.format(element_size, element_shape)

    if phased_array:
        telescope_id = telescope_id + '_array'
telescope_str = telescope_id+'_'

if ground_plane is None:
    ground_plane_str = 'no_ground_'
else:
    if ground_plane > 0.0:
        ground_plane_str = '{0:.1f}m_ground_'.format(ground_plane)
    else:
        raise ValueError('Height of antenna element above ground plane must be positive.')

if use_external_beam:
    external_beam = fits.getdata(external_beam_file, extname='BEAM_{0}'.format(beam_pol))
    external_beam_freqs = fits.getdata(external_beam_file, extname='FREQS_{0}'.format(beam_pol))
    beam_type = 'extpb'
    # if beam_chromaticity:
    #     beam_type = beam_type + '_chromatic'
    # else:
    #     beam_type = beam_type + '_achromatic'
else:
    beam_type = 'funcpb'
    # beam_type = beam_type + '_chromatic'

beam_types = [beam_type + '_' + chromaticity_str for chromaticity_str in ['achromatic','chromatic']]

if (antenna_file is None) and (array_layout is None):
    raise ValueError('One of antenna array file or layout must be specified')
if (antenna_file is not None) and (array_layout is not None):
    raise ValueError('Only one of antenna array file or layout must be specified')

if antenna_file is not None: 
    try:
        ant_info = NP.loadtxt(antenna_file, skiprows=6, comments='#', usecols=(0,1,2,3))
        ant_id = ant_info[:,0].astype(int).astype(str)
        ant_locs = ant_info[:,1:]
    except IOError:
        raise IOError('Could not open file containing antenna locations.')
else:
    if array_layout not in ['MWA-128T', 'HERA-7', 'HERA-19', 'HERA-37', 'HERA-61', 'HERA-91', 'HERA-127', 'HERA-169', 'HERA-217', 'HERA-271', 'HERA-331', 'CIRC']:
        raise ValueError('Invalid array layout specified')

    if array_layout == 'MWA-128T':
        ant_info = NP.loadtxt(rootdir+'project_MWA/MWA_128T_antenna_locations_MNRAS_2012_Beardsley_et_al.txt', skiprows=6, comments='#', usecols=(0,1,2,3))
        ant_id = ant_info[:,0].astype(int).astype(str)
        ant_locs = ant_info[:,1:]
    elif array_layout == 'HERA-7':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=7)
    elif array_layout == 'HERA-19':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=19)
    elif array_layout == 'HERA-37':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=37)
    elif array_layout == 'HERA-61':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=61)
    elif array_layout == 'HERA-91':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=91)
    elif array_layout == 'HERA-127':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=127)
    elif array_layout == 'HERA-169':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=169)
    elif array_layout == 'HERA-217':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=217)
    elif array_layout == 'HERA-271':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=271)
    elif array_layout == 'HERA-331':
        ant_locs, ant_id = RI.hexagon_generator(14.6, n_total=331)
    elif array_layout == 'CIRC':
        ant_locs, ant_id = RI.circular_antenna_array(element_size, minR, maxR=maxR)

bl, bl_id = RI.baseline_generator(ant_locs, ant_id=ant_id, auto=False, conjugate=False)
bl, select_bl_ind, bl_count = RI.uniq_baselines(bl)
bl_id = bl_id[select_bl_ind]
bl_length = NP.sqrt(NP.sum(bl**2, axis=1))
sortind = NP.argsort(bl_length, kind='mergesort')
bl = bl[sortind,:]
bl_id = bl_id[sortind]
bl_length = bl_length[sortind]
total_baselines = bl_length.size

baseline_bin_indices = range(0,total_baselines,baseline_chunk_size)

if use_HI_monopole:
    bllstr = map(str, bl_length)
    uniq_bllstr, ind_uniq_bll = NP.unique(bllstr, return_index=True)
    count_uniq_bll = [bllstr.count(ubll) for ubll in uniq_bllstr]
    count_uniq_bll = NP.asarray(count_uniq_bll)

    bl = bl[ind_uniq_bll,:]
    bl_id = bl_id[ind_uniq_bll]
    bl_length = bl_length[ind_uniq_bll]

    sortind = NP.argsort(bl_length, kind='mergesort')
    bl = bl[sortind,:]
    bl_id = bl_id[sortind]
    bl_length = bl_length[sortind]
    count_uniq_bll = count_uniq_bll[sortind]

total_baselines = bl_length.size
baseline_bin_indices = range(0, int(NP.ceil(1.0*total_baselines/baseline_chunk_size)+1)*baseline_chunk_size, baseline_chunk_size)
if n_bl_chunks is None:
    n_bl_chunks = int(NP.ceil(1.0*total_baselines/baseline_chunk_size))

bl_chunk = range(len(baseline_bin_indices)-1)
bl_chunk = bl_chunk[:n_bl_chunks]
bl = bl[:min(baseline_bin_indices[n_bl_chunks], total_baselines),:]
bl_length = bl_length[:min(baseline_bin_indices[n_bl_chunks], total_baselines)]
bl_id = bl_id[:min(baseline_bin_indices[n_bl_chunks], total_baselines)]
    
oversampling_factor = 1.0 + f_pad
n_channels = nchan

window = n_channels * DSP.windowing(n_channels, shape=bpass_shape, pad_width=0, centering=True, area_normalize=True) 
bw = n_channels * freq_resolution
bandpass_str = '{0:0d}x{1:.1f}_kHz'.format(nchan, freq_resolution/1e3)

pfb_instr = ''
pfb_outstr = ''
if pfb_method is None:
    pfb_instr = '_no_pfb'
    pfb_outstr = 'no_pfb_'

snapshot_type_str = ''
if avg_drifts:
    snapshot_type_str = 'drift_averaged_'
if beam_switch:
    snapshot_type_str = 'beam_switches_'
if snapshots_range is not None:
    snapshot_type_str = 'snaps_{0[0]:0d}-{0[1]:0d}_'.format(snapshots_range)

duration_str = ''
if obs_mode in ['track', 'drift']:
    if (t_acc is not None) and (n_acc is not None):
        duration_str = '_{0:0d}x{1:.1f}s'.format(n_acc, t_acc)

pc = NP.asarray(pc).reshape(1,-1)
if pc_coords == 'dircos':
    pc_dircos = pc
elif pc_coords == 'altaz':
    pc_dircos = GEOM.altaz2dircos(pc, units='degrees')

spindex_seed_str = ''
if spindex_rms > 0.0:
    spindex_rms_str = '{0:.1f}'.format(spindex_rms)
else:
    spindex_rms = 0.0

if spindex_seed is not None:
    spindex_seed_str = '{0:0d}_'.format(spindex_seed)

for k in range(n_sky_sectors):
    if n_sky_sectors == 1:
        sky_sector_str = '_all_sky_'
    else:
        sky_sector_str = '_sky_sector_{0:0d}_'.format(k)
    
    for beam_iter, beam_usage_str in enumerate(beam_types):

        infile = rootdir+project_dir+telescope_str+'multi_baseline_visibilities_'+ground_plane_str+snapshot_type_str+obs_mode+duration_str+'_baseline_range_{0:.1f}-{1:.1f}_'.format(bl_length[baseline_bin_indices[0]],bl_length[min(baseline_bin_indices[n_bl_chunks-1]+baseline_chunk_size-1,total_baselines-1)])+fg_str+sky_sector_str+'sprms_{0:.1f}_'.format(spindex_rms)+spindex_seed_str+'nside_{0:0d}_'.format(nside)+delaygain_err_str+'Tsys_{0:.1f}K_{1}_{2:.1f}_MHz_'.format(Tsys, bandpass_str, freq/1e6)+beam_usage_str+pfb_instr
        outfile = rootdir+project_dir+telescope_str+'multi_baseline_CLEAN_visibilities_'+ground_plane_str+snapshot_type_str+obs_mode+duration_str+'_baseline_range_{0:.1f}-{1:.1f}_'.format(bl_length[baseline_bin_indices[0]],bl_length[min(baseline_bin_indices[n_bl_chunks-1]+baseline_chunk_size-1,total_baselines-1)])+fg_str+sky_sector_str+'sprms_{0:.1f}_'.format(spindex_rms)+spindex_seed_str+'nside_{0:0d}_'.format(nside)+delaygain_err_str+'Tsys_{0:.1f}K_{1}_{2:.1f}_MHz_'.format(Tsys, bandpass_str, freq/1e6)+beam_usage_str+'_'+pfb_outstr+bpass_shape
    
        if beam_iter == 0:

            achrmia = RI.InterferometerArray(None, None, None, init_file=infile+'.fits')
            achrmia.phase_centering(phase_center=pc, phase_center_coords=pc_coords,
                                   do_delay_transform=False)   
            achrmdso = DS.DelaySpectrum(interferometer_array=achrmia)
            # achrmdso.delay_transform(oversampling_factor-1.0, freq_wts=window)
            # achrmdso.clean(pad=1.0, freq_wts=window, clean_window_buffer=3.0)
            achrmdso.delayClean(pad=1.0, freq_wts=window, clean_window_buffer=3.0)
            achrmdso.save(outfile, tabtype='BinTableHDU', overwrite=True, verbose=True)
            # achrmdso2 = DS.DelaySpectrum(init_file=outfile+'.cc.fits')
        elif beam_iter == 1:
            chrmia = RI.InterferometerArray(None, None, None, init_file=infile+'.fits')
            chrmia.phase_centering(phase_center=pc, phase_center_coords=pc_coords,
                                   do_delay_transform=False)   
            chrmdso = DS.DelaySpectrum(interferometer_array=chrmia)
            # chrmdso.delay_transform(oversampling_factor-1.0, freq_wts=window)
            # chrmdso.clean(pad=1.0, freq_wts=window, clean_window_buffer=3.0)
            chrmdso.delayClean(pad=1.0, freq_wts=window, clean_window_buffer=3.0)
            chrmdso.save(outfile, tabtype='BinTableHDU', overwrite=True, verbose=True)
            # chrmdso = DS.DelaySpectrum(init_file=outfile+'.cc.fits')
    
fig = PLT.figure()
ax = fig.add_subplot(111)
noiseless_dspec = ax.pcolorfast(achrmdso.ia.baseline_lengths, 1e9*achrmdso.lags, NP.abs(achrmdso.cc_skyvis_net_lag[:-1,:-1,0].T), norm=PLTC.LogNorm(vmin=NP.abs(achrmdso.cc_skyvis_net_lag).min(), vmax=NP.abs(achrmdso.cc_skyvis_net_lag).max()))
horizonb = ax.plot(achrmdso.ia.baseline_lengths, 1e9*achrmdso.horizon_delay_limits[0,:,0], color='black', ls='--', lw=2.5)
horizonb = ax.plot(achrmdso.ia.baseline_lengths, 1e9*achrmdso.horizon_delay_limits[0,:,1], color='black', ls='--', lw=2.5)
ax.set_xlabel(r'$|b|$ [m]', fontsize=16, weight='medium')
ax.set_ylabel(r'$\tau$ [ns]', fontsize=16, weight='medium')

cbax = fig.add_axes([0.91, 0.125, 0.02, 0.74])
cbar = fig.colorbar(noiseless_dspec, cax=cbax, orientation='vertical')
cbax.set_xlabel('Jy Hz', labelpad=10, fontsize=12)
cbax.xaxis.set_label_position('top')
fig.subplots_adjust(right=0.88)
PLT.savefig(rootdir+project_dir+'figures/achromatic_wedge.png', bbox_inches=0)

fig = PLT.figure()
ax = fig.add_subplot(111)
noiseless_dspec = ax.pcolorfast(chrmdso.ia.baseline_lengths, 1e9*chrmdso.lags, NP.abs(chrmdso.cc_skyvis_net_lag[:-1,:-1,0].T), norm=PLTC.LogNorm(vmin=NP.abs(chrmdso.cc_skyvis_net_lag).min(), vmax=NP.abs(chrmdso.cc_skyvis_net_lag).max()))
horizonb = ax.plot(chrmdso.ia.baseline_lengths, 1e9*chrmdso.horizon_delay_limits[0,:,0], color='black', ls='--', lw=2.5)
horizonb = ax.plot(chrmdso.ia.baseline_lengths, 1e9*chrmdso.horizon_delay_limits[0,:,1], color='black', ls='--', lw=2.5)
ax.set_xlabel(r'$|b|$ [m]', fontsize=16, weight='medium')
ax.set_ylabel(r'$\tau$ [ns]', fontsize=16, weight='medium')

cbax = fig.add_axes([0.91, 0.125, 0.02, 0.74])
cbar = fig.colorbar(noiseless_dspec, cax=cbax, orientation='vertical')
cbax.set_xlabel('Jy Hz', labelpad=10, fontsize=12)
cbax.xaxis.set_label_position('top')
fig.subplots_adjust(right=0.88)
PLT.savefig(rootdir+project_dir+'figures/chromatic_wedge.png', bbox_inches=0)

colrs = ['blue', 'green', 'red']
fig,axs = PLT.subplots(ncols=3, sharex=True, sharey=True)
for bli in range(0,3):
    axs[bli].plot(1e9*achrmdso.lags, NP.abs(achrmdso.cc_skyvis_net_lag[bli,:,0]), marker='.', color='green')
    axs[bli].plot(1e9*chrmdso.lags, NP.abs(chrmdso.cc_skyvis_net_lag[bli,:,0]), marker='+', color='blue')
    axs[bli].set_xlim(-250,250)
    axs[bli].set_ylim(1e5,1e10)
    axs[bli].set_yscale('log')
fig.subplots_adjust(wspace=0, hspace=0)
big_ax = fig.add_subplot(111)
big_ax.set_axis_bgcolor('none')
big_ax.tick_params(labelcolor='none', top='off', bottom='off', left='off', right='off')
big_ax.set_xticks([])
big_ax.set_yticks([])
big_ax.set_xlabel(r'$\tau$ [$\mu$s]', fontsize=16, weight='medium', labelpad=30)
big_ax.set_ylabel(r'$V(\tau)$ [Jy Hz]', fontsize=16, weight='medium', labelpad=20)

# ax.set_xlabel(r'$\tau$ [ns]', fontsize=16, weight='medium')
# ax.set_ylabel(r'$V(\tau)$ [Jy Hz]', fontsize=16, weight='medium')
PLT.savefig(rootdir+project_dir+'figures/14.6m_delay_spectra.png', bbox_inches=0)

NP.savez_compressed(rootdir+project_dir+'HERA-19_FG_delay_spectra.npz', baselines=achrmdso.ia.baselines, lst=achrmdso.ia.lst, freqs=achrmdso.f, lags=achrmdso.lags, achromatic_skyvis_freq=achrmdso.ia.skyvis_freq, achromatic_cc_skyvis_lag=achrmdso.cc_skyvis_net_lag, chromatic_skyvis_freq=chrmdso.ia.skyvis_freq, chromatic_cc_skyvis_lag=chrmdso.cc_skyvis_net_lag)

PDB.set_trace()
