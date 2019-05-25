import argparse
import sys, os, time
sys.path.append("/home/guillefix/code/beatsaber/base")
sys.path.append("/home/guillefix/code/beatsaber/base/models")
sys.path.append("/home/guillefix/code/beatsaber")
from options.train_options import TrainOptions
from data import create_dataset, create_dataloader
from models import create_model
import json, pickle
import librosa
import torch
import numpy as np
import Constants
from level_generation_utils import make_level_from_notes

from stateSpaceFunctions import feature_extraction_hybrid_raw,feature_extraction_mel,feature_extraction_hybrid

parser = argparse.ArgumentParser(description='Generate Beat Saber level from song')
parser.add_argument('--experiment_name', type=str)
parser.add_argument('--experiment_name2', type=str, default=None)
parser.add_argument('--checkpoint', type=str, default="latest")
parser.add_argument('--checkpoint2', type=str, default="latest")
parser.add_argument('--temperature', type=float, default=1.00)
parser.add_argument('--bpm', type=float, default=None)
parser.add_argument('--two_stage', action="store_true")

args = parser.parse_args()

if args.two_stage:
    assert args.experiment_name2 is not None
    assert args.checkpoint2 is not None

experiment_name = args.experiment_name+"/"
checkpoint = args.checkpoint
temperature=args.temperature
## debugging helpers
# checkpoint = "64000"
# checkpoint = "246000"
# temperature = 1.00
# experiment_name = "block_placement/"
# experiment_name = "block_selection/"
# args = {"experiment_name": experiment_name, "temperature": temperature, "checkpoint": checkpoint}
# class Struct:
#     def __init__(self, **entries):
#         self.__dict__.update(entries)
# args = Struct(**args)
song_name = "43_fixed"
song_name = "test_song"+song_name+".wav"
song_path = "../../"+song_name
print(experiment_name)

''' LOAD MODEL, OPTS, AND WEIGHTS (for stage1 if two_stage) '''
#%%

#loading opt object from experiment
opt = json.loads(open(experiment_name+"opt.json","r").read())
opt["gpu_ids"] = [0]
opt["cuda"] = True
class Struct:
    def __init__(self, **entries):
        self.__dict__.update(entries)
opt = Struct(**opt)

if args.two_stage:
    assert opt.binarized

model = create_model(opt)
model.setup()
if opt.model=='wavenet' or opt.model=='adv_wavenet':
    if not opt.gpu_ids:
        receptive_field = model.net.receptive_field
    else:
        receptive_field = model.net.module.receptive_field
else:
    receptive_field = 1

checkpoint = "iter_"+checkpoint
model.load_networks(checkpoint)

''' GET SONG FEATURES '''
#%%

y_wav, sr = librosa.load(song_path, sr=16000)

from test_song_bpms import bpms

# useful quantities
if args.bpm is not None:
    bpm = args.bpm
else:
    bpm = bpms[song_number]
feature_name = opt.feature_name
feature_size = opt.feature_size
use_sync=opt.using_sync_features
sampling_rate = opt.sampling_rate
beat_subdivision = opt.beat_subdivision
sr = sampling_rate
beat_duration = 60/bpm #beat duration in seconds

beat_duration_samples = int(60*sr/bpm) #beat duration in samples
# duration of one time step in samples:
hop = int(beat_duration_samples * 1/beat_subdivision)
if not use_sync:
    hop -= hop % 32
# num_samples_per_feature = hop

step_size = beat_duration/beat_subdivision #one vec of mfcc features per 16th of a beat (hop is in num of samples)

# get feature
state_times = np.arange(0,y_wav.shape[0]/sr,step=step_size)
if opt.feature_name == "chroma":
    if use_sync:
        features = feature_extraction_hybrid(y_wav,sr,state_times,bpm,beat_discretization=1/beat_subdivision,mel_dim=12)
    else:
        features = feature_extraction_hybrid_raw(y_wav,sr,bpm)
elif opt.feature_name == "mel":
    assert use_sync
    # features = feature_extraction_hybrid(y_wav,sr,state_times,bpm,beat_subdivision=beat_subdivision,mel_dim=12)
    features = feature_extraction_mel(y_wav,sr,state_times,bpm,mel_dim=feature_size,beat_discretization=1/beat_subdivision)


''' GENERATE LEVEL '''
#%%
song = torch.tensor(features).unsqueeze(0)

#generate level
first_samples = torch.full((1,opt.output_channels,receptive_field),Constants.START_STATE)
# stuff for older models (will remove at some point:)
# first_samples = torch.full((1,opt.output_channels,receptive_field),Constants.EMPTY_STATE)
# first_samples[0,0,0] = Constants.START_STATE
if opt.concat_outputs:
    output = model.net.module.generate(song.size(-1)-opt.time_shifts+1,song,time_shifts=opt.time_shifts,temperature=temperature,first_samples=first_samples)
else:
    output = model.net.module.generate_no_autoregressive(song.size(-1)-opt.time_shifts+1,song,time_shifts=opt.time_shifts,temperature=temperature,first_samples=first_samples)
states_list = output[0,:,:].permute(1,0)

#if using reduced_state representation convert from reduced_state_index to state tuple
unique_states = pickle.load(open("../stateSpace/sorted_states.pkl","rb"))
#old (before transformer)
# states_list = [(unique_states[i[0].int().item()-1] if i[0].int().item() != 0 else tuple(12*[0])) for i in states_list ]

#convert from states to beatsaber notes
if opt.binarized: # for experiments where the output is state/no state
    notes = [[{"_time":float((i+0.0)*bpm*hop/(sr*60)), "_cutDirection":1, "_lineIndex":1, "_lineLayer":1, "_type":0}] for i,x in enumerate(states_list) if x[0].int().item() not in [0,1,2,3]]
    # times_beat = [float((i+0.0)*bpm*hop/(sr*60)) for i,x in enumerate(states_list) if x[0].int().item() not in [0,1,2,3]]
    times_real = [float((i+0.0)*hop/sr) for i,x in enumerate(states_list) if x[0].int().item() not in [0,1,2,3]]
else: # this is where the notes are generated for end-to-end models that actually output states
    states_list = [(unique_states[i[0].int().item()-4] if i[0].int().item() not in [0,1,2,3] else tuple(12*[0])) for i in states_list ]
    notes = [[{"_time":float((i+0.0)*bpm*hop/(sr*60)), "_cutDirection":int((y-1)%9), "_lineIndex":int(j%4), "_lineLayer":int(j//4), "_type":int((y-1)//9)} for j,y in enumerate(x) if (y!=0 and y != 19)] for i,x in enumerate(states_list)]
    notes += [[{"_time":float((i+0.0)*bpm*hop/(sr*60)), "_lineIndex":int(j%4), "_lineLayer":int(j//4), "_type":3} for j,y in enumerate(x) if y==19] for i,x in enumerate(states_list)]
notes = sum(notes,[])

print("Number of generated notes: ", len(notes))

json_file = make_level_from_notes(notes, bpm, song_name, opt, args)

#%%

''' STAGE TWO! '''

if args.two_stage:
    ''' LOAD MODEL, OPTS, AND WEIGHTS (for stage2 if two_stage) '''
    experiment_name = args.experiment_name2+"/"
    checkpoint = args.checkpoint2
    #%%

    #loading opt object from experiment
    opt = json.loads(open(experiment_name+"opt.json","r").read())
    # extra things Beam search wants
    opt["gpu_ids"] = [0]
    opt["cuda"] = True
    opt["batch_size"] = 1
    opt["beam_size"] = 5
    opt["n_best"] = 5
    class Struct:
        def __init__(self, **entries):
            self.__dict__.update(entries)
    opt = Struct(**opt)

    if args.two_stage:
        assert opt.binarized

    model = create_model(opt)
    model.setup()
    if opt.model=='wavenet' or opt.model=='adv_wavenet':
        if not opt.gpu_ids:
            receptive_field = model.net.receptive_field
        else:
            receptive_field = model.net.module.receptive_field
    else:
        receptive_field = 1

    checkpoint = "iter_"+checkpoint2
    model.load_networks(checkpoint2)

    # generated_folder = "generated/"
    # signature_string = song_name+"_"+opt.model+"_"+opt.dataset_name+"_"+opt.experiment_name+"_"+str(temperature)+"_"+checkpoint
    # json_file = generated_folder+"test_song"+signature_string+".json"

    # import imp; import stateSpaceFunctions; imp.reload(stateSpaceFunctions)
    # import imp; import transformer.Translator; imp.reload(transformer.Translator)
    # import transformer.Beam; imp.reload(transformer.Beam)
    unique_states = pickle.load(open("../stateSpace/sorted_states.pkl","rb"))

    ## results of Beam search
    # can we add some stochasticity to beam search maybe?
    generated_sequences = model.generate(features, json_file, bpm, unique_states, generate_full_song=False)

    #%%
    from stateSpaceFunctions import stage_two_states_to_json_notes
    notes = stage_two_states_to_json_notes(generated_sequences[0], state_times, bpm, hop, sr, state_rank=unique_states)
    # remake level with actual notes from stage 2 now
    make_level_from_notes(notes, bpm, song_name, opt, args)
