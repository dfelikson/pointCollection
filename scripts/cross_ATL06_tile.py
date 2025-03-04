#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Wed May  1 10:40:57 2019

@author: ben
"""

import pointCollection as pc

import numpy as np
import os
import h5py
#import matplotlib.pyplot as plt
import glob
#import re
#import sys

def ATL06_crossovers(files, different_cycles=False, delta_time_max=np.inf, n_extra_segments=0):
    D=[]
    with h5py.File(files[0],'r') as h5f:
        fields=list(h5f[list(h5f.keys())[0]].keys())

    for file in files:
        D += pc.reconstruct_ATL06_tracks(\
            pc.indexedH5.data(filename=file).read(None, fields=fields ))
    for Di in D:
        # set the along-track dh filter to calculate the differences, but not to edit the data
        along_track_dh_filter(Di, threshold=None,  to_nan=False)
        Di.assign({'time':Di.delta_time})
        Di.index(np.isfinite(Di.h_li))
    xover_list=list()
    #plt.clf()
    for ii in np.arange(len(D)):
        for jj in np.arange(len(D)):
            if np.abs(D[ii].delta_time[0] - D[jj].delta_time[0]) > delta_time_max:
                continue
            if (D[ii].size <2) or (D[jj].size < 2) or (ii>=jj) or (D[ii].rgt[0]==D[jj].rgt[0]):
                continue
            if different_cycles and D[ii].cycle_number[0]==D[jj].cycle_number[0]:
                continue
            xyC, inds, L=pc.cross_tracks([D[ii], D[jj]], delta=20, delta_coarse=1000)
            if xyC is not None:
                try:
                    xover_list.append({'xyC':xyC, 'data_0':D[ii][inds[0]], 'data_1':D[jj][inds[1]], 'L0':L[0], 'L1':L[1]})
                    if n_extra_segments > 0:
                        xover_list[-1]['data_0_extra_segments'] = list()
                        xover_list[-1]['data_1_extra_segments'] = list()
                        for kk in np.concatenate([np.arange(inds[0][0]-n_extra_segments, inds[0][0]), np.arange(inds[0][1]+1, inds[0][1]+n_extra_segments+1)]):
                            if kk >= 0 and kk < D[ii].shape[0]:
                                xover_list[-1]['data_0_extra_segments'].append(D[ii][kk])
                            else:
                                xover_list[-1]['data_0_extra_segments'].append(pc.data())

                        for kk in np.concatenate([np.arange(inds[1][0]-n_extra_segments, inds[1][0]), np.arange(inds[1][1]+1, inds[1][1]+n_extra_segments+1)]):
                            if kk >= 0 and kk < D[jj].shape[0]:
                                xover_list[-1]['data_1_extra_segments'].append(D[jj][kk])
                            else:
                                xover_list[-1]['data_1_extra_segments'].append(pc.data())
                        xover_list[-1]['data_0_extra_segments'] = pc.data().from_list(xover_list[-1]['data_0_extra_segments'])
                        xover_list[-1]['data_1_extra_segments'] = pc.data().from_list(xover_list[-1]['data_1_extra_segments'])
                except Exception as e:
                    print("# ATL06_crossovers: caught exception:" + str(e.__class__) + ' '+str(e))
    return xover_list


def write_xovers(xover_list, out_file, n_extra_segments=0):
    if os.path.isfile(out_file):
        os.remove(out_file)
    with h5py.File(out_file,'w') as h5f:
        for key_D in ['data_0', 'data_1']:
            group='/'+key_D
            h5f.create_group(group)

            key_L=key_D.replace('data_','L')
            L=np.c_[[item[key_L] for item in xover_list]]

            Dtemp=[item[key_D] for item in xover_list]
            Dtemp=pc.data().from_list(Dtemp)
            shape=[np.int64(Dtemp.size/2), 2]
            Dtemp.shape=shape
            for key in Dtemp.fields:
                temp=getattr(Dtemp, key)
                temp.shape=shape
                h5f.create_dataset(group+'/'+key, data=temp)
            h5f.create_dataset(group+'/W', data=np.c_[1-L, L])

        if n_extra_segments > 0:
            for key_D in ['data_0_extra_segments', 'data_1_extra_segments']:
                group='/'+key_D
                h5f.create_group(group)

                Dtemp=[item[key_D] for item in xover_list]
                Dtemp=pc.data().from_list(Dtemp)
                shape=[np.int64(Dtemp.size/(n_extra_segments*2)), n_extra_segments*2]
                Dtemp.shape=shape
                for key in Dtemp.fields:
                    temp=getattr(Dtemp, key)
                    temp.shape=shape
                    h5f.create_dataset(group+'/'+key, data=temp)

        xy=np.c_[[item['xyC'] for item in xover_list]]
        h5f.create_dataset('/x', data=xy[:,0])
        h5f.create_dataset('/y', data=xy[:,1])
        try:
            h5f.create_dataset('/slope_x', data=np.array([item['slope_x'] for item in xover_list]))
            h5f.create_dataset('/slope_y', data=np.array([item['slope_y'] for item in xover_list]))
            h5f.create_dataset('/masked', data=np.array([item['masked'] for item in xover_list]))
        except Exception as e:
            print("# write_xovers: caught exception:" + str(e.__class__) + ' '+str(e))
    return #xover_list

def read_xovers(xover_dir):

    tiles=glob.glob(xover_dir+'/*.h5')
    with h5py.File(tiles[0],'r') as h5f:
        fields=[key for key in h5f['D0'].keys()]
    D=[]
    X=[]
    for tile in glob.glob(xover_dir+'/*.h5'):
        D.append([pc.data().from_file(tile, field_dict={gr : fields}) for gr in ['D0','D1']])
        with h5py.open(tile,'r') as h5f:
            X.append(pc.data(fields=['x','y']).from_file(tile,field_dict={None:['x','y']}))
    return D, X

def make_queue(files, args):

    if not os.path.isdir(args.out_dir):
        os.mkdir(args.out_dir)

    for file in files:
        if os.path.isfile(args.out_dir+'/'+os.path.basename(file)):
            continue
        # N.B.  this requires that cross_ATL06_tile is on the unix path.
        this_str = 'cross_ATL06_tile.py %s %s ' %   (file, args.out_dir)
        if args.hemisphere is not None:
            this_str += f" -H {args.hemisphere}"
        if args.different_cycles_only:
            this_str += " --different_cycles_only "
        if args.mask_file is not None:
            this_str += f" --mask_file {args.mask_file}"
    print(this_str)

def calc_slope(xovers, mask_file, mask_value=1, hemisphere=-1):

    if hemisphere==-1:
        dx=1.e4
    else:
        dx=90

    xy=np.c_[[item['xyC'] for item in xovers]]

    mask=pc.grid.data().from_geotif(mask_file, \
                bounds=[[np.min(xy[:,0].ravel())-dx, np.max(xy[:,0].ravel()+dx)], [np.min(xy[:,1].ravel())-dx, np.max(xy[:,1].ravel()+dx)]])
    try:
        masked=np.abs(mask.interp(xy[:,0], xy[:,1])-mask_value)<.01
    except AttributeError:
        print(f"\cross_ATL06_tile.py: no data found in mask file {mask_file}, marking all crossovers as masked\n")
        masked=np.zeros(xy.shape[0], dtype=bool)

    G=np.zeros((4,4))
    G[:,2]=np.array([1, 1, 0, 0])
    G[:,3]=np.array([0, 0, 1, 1])
    for ii, xo in enumerate(xovers):
        x1=np.r_[xo['data_0'].x, xo['data_1'].x]
        y1=np.r_[xo['data_0'].y, xo['data_1'].y]
        G[:,0]=x1-x1.mean()
        G[:,1]=y1-y1.mean()
        m=np.linalg.solve(G, np.r_[xo['data_0'].h_li, xo['data_1'].h_li])
        xo['slope_x'] = m[0]
        xo['slope_y'] = m[1]
        xo['masked'] = masked[ii]

def along_track_dh_filter(D, threshold=None, to_nan=False):
    ss_dh=np.zeros(D.shape)
    n_pts=D.size
    if n_pts <= 1:
        D.assign({'rss_along_track_dh': ss_dh})
        return
    i0=slice(1, n_pts-1)
    for ii in [-1, 1]:
        i1=slice(1+ii, n_pts-1+ii)
        dx=D.x_atc[i0]-D.x_atc[i1]
        ss_dh[i0] += (D.h_li[i0]-D.dh_fit_dx[i0]*dx-D.h_li[i1])**2
    ss_dh[0]=(D.h_li[1]-D.h_li[0] - (D.x_atc[1]-D.x_atc[0])*D.dh_fit_dx[0])**2
    ss_dh[-1]=(D.h_li[-1]-D.h_li[-2] - (D.x_atc[-1]-D.x_atc[-2])*D.dh_fit_dx[-1])**2
    rss_dh = np.sqrt(ss_dh)
    D.assign({'rss_along_track_dh': rss_dh})
    if threshold is not None:
        D.valid[rss_dh>threshold]=0
    if to_nan:
        D.h_li[rss_dh>threshold]=np.NaN


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Find crossovers in an ATL06 tile')
    parser.add_argument('tile_glob', type=str, help="glob which matches the tiles")
    parser.add_argument('out_dir', type=str, help="output directory")
    parser.add_argument('--mask_file', '-m', help="mask file identifying points of interest")
    parser.add_argument('--mask_value', '-v', type=int, help="mask value identifying points of interest", default=1)
    parser.add_argument('--hemisphere', '-H', type=int, help="hemisphere, -1 for Antarctica, 1, for Arctic")
    parser.add_argument('--different_cycles_only','-d', action='store_true', help="Calculate crossovers only for tracks from different cycles")
    parser.add_argument('--delta_time_max','-dtm', type=float, help="Maximum delta time between crossover measurements", default=np.inf)
    parser.add_argument('--n_extra_segments','-n', type=int, help="Number of extra ATL06 segments to include on either side of crossover", default=0)
    parser.add_argument('--queue','-q', action="store_true")
    args=parser.parse_args()

    out_dir=args.out_dir
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)

    files=[]
    for temp in args.tile_glob.split(' '):
        files += glob.glob(temp)

    if args.queue:
        make_queue(files, args)
        return

    xover_list = ATL06_crossovers(files, different_cycles=args.different_cycles_only, delta_time_max=args.delta_time_max, n_extra_segments=args.n_extra_segments)
    if len(xover_list) > 0:
        if args.hemisphere is not None:
            calc_slope(xover_list, args.mask_file, mask_value=args.mask_value, hemisphere=args.hemisphere)

        write_xovers(xover_list, os.path.join(out_dir, os.path.basename(files[0])), n_extra_segments=args.n_extra_segments)


if __name__=='__main__':
    main()
