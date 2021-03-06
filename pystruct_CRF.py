#!/bin/python
# author:       Stephanie Hyland (sh985@cornell.edu)
# date:         April 2014
# description:  Binary classification for CACs using a conditional random field (CRF).
#               A graph consists of all calcifications from a single patient.
#               Calcifications are connected in the graph if within "radius" of each other.
# input:        Comma-separated file, one row per calcification, with patient IDs and labels.
# result:       Performance evaluation on a test/train split of the input data.
#
# todo:         1. n-fold cross-validation.
#               2. proper treatment of features

import pystruct
#from pystruct.models import GraphCRF
from pystruct.models import EdgeFeatureGraphCRF
from pystruct.learners import OneSlackSSVM
from pystruct.learners import NSlackSSVM
from pystruct.plot_learning import plot_learning
from sklearn.cross_validation import StratifiedKFold
import sys
import numpy as np
import random
import math

# --- Parameters --- #
# the patient id is the final column
id_col = -1
# label is the second last column
label_col = -2
# feature indices...
geometric_features = [1,2,3,4,12,13,14]
spatial_features = [5,6,7,15]
intensity_features = [8,9,10,11]
# which features to use?
# THIS IS AN INEFFICIENT MESS
#which_features = 'spatial_only'
#feature_indices = spatial_features
#which_features = 'geometric_only'
#feature_indices = geometric_features
#which_features = 'intensity_only'
#feature_indices = intensity_features
#which_features = 'geometric_and_intensity_only'
#feature_indices = geometric_features+intensity_features
which_features = 'all_only'
feature_indices = geometric_features+spatial_features+intensity_features
feature_indices.sort()
# spatial indices, for calculating distances (we should be losing these anyway)
space_indices = [16,17,18]
mindist_index = 15
# what features to use? (select this!)
n_features = len(feature_indices)
# for the structural information... what cutoff radii to use?
#radii = [10,20,50,100,150,200,350]
#radii = [10]
radii = map(float,sys.argv[2:])
#radii = [0]
n_edge_features = len(radii)
# how many states (2)
n_states = 2
# how many xval?
n_splits = 10
# how much output to give
verbose=False

# --- Inputs --- #
if len(sys.argv)<2:
    sys.exit("Datafile, yo!")

# datafile
datapath=sys.argv[1]
# radius for 'neighbourness'? (atm totally arbitrary)
#radius = float(sys.argv[2])

# --- Functions --- #
def include_structure(X,radii):
    n_node = X.shape[0]
    edges = []
    edge_features = []
    for n in xrange(n_node):
        for nn in xrange(n+1,n_node):
            this_edge_features = []
            distance = np.linalg.norm(X[n,space_indices]-X[nn,space_indices])
            prevrad=0
            for radius in radii:
                if prevrad < distance and distance <= radius:
                    this_edge_features.append(1)
                else:
                    this_edge_features.append(0)
                prevrad=radius
            # if n has a higher yl than nn... this is not a symmetric edge feature so i should probably look into that a bit more.
#            if X[n,15]>X[nn,15]:
#                this_edge_features.append(1)
#            else:
#                this_edge_features.append(0)
            edge_features.append(this_edge_features)
            # we have an edge between all nodes...
            edges.append((n,nn)) 

    edge_features_array = np.array(edge_features)
    edges_array = np.array(edges)
    return edges_array, edge_features_array

# this is defunct
def get_neighbours(X):
    n_node = X.shape[0]
    nbs = []
    for n in xrange(n_node):
        for nn in xrange(n+1,n_node):
            distance = np.linalg.norm(X[n,space_indices]-X[nn,space_indices])
            if distance<radius:
                nbs.append((n,nn))
    return nbs

def prepare_data(datafile):
    header = datafile.readline()
    data = dict()
    for line in datafile:
        splitline = line.strip().split(',')
        # each patient is a graph example
        patient_id = splitline[id_col]
        try:
            data[patient_id].append(splitline)
        except KeyError:
            data[patient_id] = [splitline]

    examples = []
    labels = []
    for patient in data:
        patient_data = np.array(data[patient],dtype=float)
        node_features = patient_data[:,feature_indices]
       # edges = np.array(get_neighbours(all_features))
        edges, edge_features = include_structure(patient_data,radii)
       # edge_features = get_edge_features(patient_data[:,space_indices],edges)
        example = (node_features,edges,edge_features)
        if edges.shape[0]>0:
            examples.append(example)
            labels.append(1*(patient_data[:,label_col]==0).astype(np.int32))
   
    return examples, labels

def get_contingency(pred,true):
    pos = np.where(true==1)
    neg = np.where(true==0)
    TP = sum(pred[pos]==1)
    FP = sum(pred[neg]==1)
    TN = sum(pred[neg]==0)
    FN = sum(pred[pos]==0)
    return np.array([TP,FP,TN,FN])

# going to include stratification here, based on the mean # CACs...
def stratified_split(n_examples,n_splits,labels):
    # this gives the fraction of the calc in the patient which are CAC
    mean_cac = np.array(map(np.mean,labels))

    zeroes = np.where(mean_cac==0)[0]
    ones = np.where(mean_cac==1)[0]
    lthalf = np.where((mean_cac<0.5)&(mean_cac!=0))[0]
    gthalf = np.where((mean_cac>=0.5)&(mean_cac!=1))[0]

    zeroes_shuff = np.random.permutation(zeroes)
    ones_shuff = np.random.permutation(ones)
    lthalf_shuff = np.random.permutation(lthalf)
    gthalf_shuff = np.random.permutation(gthalf)

    altogether = [zeroes_shuff,ones_shuff,lthalf_shuff,gthalf_shuff]
#    altogether = [np.random.permutation(n_examples)]
    indices = []
    if n_splits==1:
        nn_splits=10
    else:
        nn_splits = n_splits

    for i in xrange(n_splits):
        test = []
        train = []
        for subclass in altogether:
            n_examples = len(subclass)
            n_test = int(math.floor(float(n_examples/nn_splits)))
            test_indices = subclass[i*n_test:(i+1)*n_test].tolist()
            train_indices = [j for j in subclass if not j in test_indices]
            test = test + test_indices
            train = train + train_indices
        indices.append((test,train))

    # end case, mop it up
    test = []
    train = []
    for subclass in altogether:
        n_examples = len(subclass)
        n_test = int(math.floor(float(n_examples/nn_splits)))
        test_indices = subclass[(i+1)*n_test:].tolist()
        train_indices = [i for i in subclass if not i in test_indices]
        test = test + test_indices
        train = train + train_indices
    indices.append((test,train))
    return indices

# --- Data prep --- #
datafile = open(datapath,'rU')
examples, labels = prepare_data(datafile)
n_examples = len(examples)

if verbose:
    print "n_examples",n_examples
#    print "n_train:",len(train_indices)     #update!
#    print "n_test:",len(test_indices)       #update!
    print "xval:", n_splits

sens_all = []
spec_all = []
acc_all = []
rec_all = []
prec_all = []
n_edges_all = []

# --- Ready for xval! --- #
indices = stratified_split(n_examples,n_splits,labels)

for i in xrange(n_splits):
    train = indices[i][0]
    test = indices[i][1]

    mean_cac = np.array(map(np.mean,labels))

    # sure there's a more efficient way to do this
    # --- Test/train split --- #
    X_train = [examples[j] for j in train]
    Y_train = [labels[j] for j in train]
    X_test = [examples[j] for j in test]
    Y_test = [labels[j] for j in test]
#    if verbose:
#        print np.mean(map(np.mean,Y_train)), 'pm',np.var(map(np.mean,Y_train))
#        print np.mean(map(np.mean,Y_test)), 'pm',np.var(map(np.mean,Y_test))
    
    # --- Train model --- #
    model = EdgeFeatureGraphCRF(n_states,n_features,n_edge_features)
    ssvm = NSlackSSVM(model=model, C=0.1, tol=0.001, verbose=0,show_loss_every=10)
#    ssvm = OneSlackSSVM(model=model, C=.1, inference_cache=50, tol=0.1, verbose=0,show_loss_every=10)
    ssvm.fit(X_train, Y_train)

    # --- Test with pystruct --- #
#        print("Test score with graph CRF: %f" % ssvm.score(X_test, Y_test))

    # --- Test manually - get contingency tables --- #
    prediction = ssvm.predict(X_test)

    contingency = np.array([0,0,0,0])
    for i in xrange(len(test)):
        pred = prediction[i]
        true = Y_test[i]
        contingency = contingency+get_contingency(pred,true)

    TP, FP, TN, FN = contingency[0], contingency[1], contingency[2], contingency[3]

#        sens = float(TP)/(TP+FN)
#        sens_all.append(sens)
#        spec = float(TN)/(FP+TN)
#        spec_all.append(spec)
    acc = float(TP+TN)/(TP+FP+TN+FN)
    acc_all.append(acc)
    prec = float(TP)/(TP+FP)
    prec_all.append(prec)
    rec = float(TP)/(TP+FN)
    rec_all.append(rec)
    
#        print "train mean: %2.3f" %np.mean(map(len,Y_train)),"max:", max(map(len,Y_train)), "min:",min(map(len,Y_train)), "n:", sum(map(len,Y_train)), "mean_cac:", np.mean(map(sum,Y_train))
#        print "test mean:  %2.3f" %np.mean(map(len,Y_test)),"max:", max(map(len,Y_test)), "min:",min(map(len,Y_test)), "sens: %2.3f" %sens

#        print("Sensitivity: %f" % sens)
#        print("Specificity: %f" % spec)
#        print "Contingency table: (TP FP TN FN):", contingency
    #plot_learning(ssvm,time=True)

if verbose:
    print 'Feature set:', which_features
    print 'Radii:', ','.join(map(str,radii))
    print 'accuracy: \t%2.3f' % np.mean(acc_all), 'pm %2.3f' % np.var(acc_all)
    print 'precision: \t%2.3f' % np.mean(prec_all), 'pm %2.3f' % np.var(prec_all)
    print 'recall: \t%2.3f' % np.mean(rec_all), 'pm %2.3f' % np.var(rec_all)

print ','.join(map(str,radii)), np.mean(acc_all), "acc", which_features
print ','.join(map(str,radii)), np.mean(prec_all), "prec", which_features
print ','.join(map(str,radii)), np.mean(rec_all), "rec", which_features
