import numpy as np
import librosa
from pathlib import Path
import json
import os.path
import sys
import argparse

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(os.path.join(THIS_DIR, os.pardir), os.pardir))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
EXTRACT_DIR = os.path.join(DATA_DIR, 'extracted_data')
if not os.path.isdir(DATA_DIR):
    os.mkdir(DATA_DIR)
if not os.path.isdir(EXTRACT_DIR):
    os.mkdir(EXTRACT_DIR)
sys.path.append(ROOT_DIR)
from scripts.feature_extraction.feature_extraction import extract_features_hybrid, extract_features_mel,extract_features_hybrid_beat_synced, extract_features_multi_mel

from scripts.feature_extraction.feature_extraction import extract_features_hybrid, extract_features_mel,extract_features_hybrid_beat_synced, extract_features_multi_mel

from scripts.training.data.level_processing_functions import get_raw_binary_classes_reduced_tensors_from_level

parser = argparse.ArgumentParser(description="Preprocess songs data")

parser.add_argument("data_path", type=str, help="Directory contining Beat Saber level folders")
parser.add_argument("difficulties", type=str, help="Comma-separated list of difficulties to process (e.g. \"Expert,Hard\"")
parser.add_argument("--feature_name", metavar='', type=str, default="mel", help="mel, chroma, multi_mel")
parser.add_argument("--feature_size", metavar='', type=int, default=100)
parser.add_argument("--sampling_rate", metavar='', type=float, default=44100.0)
parser.add_argument("--beat_subdivision", metavar='', type=int, default=16)
parser.add_argument("--step_size", metavar='', type=float, default=0.01)
parser.add_argument("--replace_existing", action="store_true")
parser.add_argument("--using_bpm_time_division", action="store_true")

args = parser.parse_args()

# makes arugments into global variables of the same name, used later in the code
globals().update(vars(args))
data_path = Path(data_path)

## distributing tasks accross nodes ##
from mpi4py import MPI
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
print(rank)
print("creating tensorblocks")

#assuming egg sound format, as used in new BeatSaber format
candidate_audio_files = sorted(data_path.glob('**/*.egg'), key=lambda path: path.parent.__str__())
num_tasks = len(candidate_audio_files)
num_tasks_per_job = num_tasks//size
tasks = list(range(rank*num_tasks_per_job,(rank+1)*num_tasks_per_job))
if rank < num_tasks%size:
    tasks.append(size*num_tasks_per_job+rank)

for i in tasks:
    path = candidate_audio_files[i]
    song_file_path = path.__str__()
    # feature files are going to be saved as numpy files
    features_file = song_file_path+"_"+feature_name+"_"+str(feature_size)+".npy"
    # blocks_reduced_file = song_file_path+"_"+difficulties+"_blocks_reduced_.npy"
    blocks_reduced_classes_file = song_file_path+difficulties+"_blocks_reduced_classes_.npy"

    level_file_found = False
    # find level files with target difficulties that exist
    for diff in difficulties.split(","):
        if Path(path.parent.__str__()+"/"+diff+".dat").is_file():
            level = list(path.parent.glob('./'+diff+'.dat'))[0]
            level = level.__str__()
            info_file = list(path.parent.glob('./info.dat'))[0]
            info_file = info_file.__str__()
            level_file_found = True
    if not level_file_found:
        continue

    if replace_existing or not os.path.isfile(blocks_reduced_classes_file):# or not os.path.isfile(blocks_reduced_file):
        print("creating feature file",i, "for level",level)
        # get level
        level = json.load(open(level, 'r'))
        notes = level["_notes"]
        info = json.load(open(info_file, 'r'))
        receptive_field = 1

        # get song
        y_wav, sr = librosa.load(song_file_path, sr=sampling_rate)

        bpm = info['_beatsPerMinute']
        sr = sampling_rate
        hop = int(sr * step_size)

        y = np.load(features_file)
        sequence_length = y.shape[-1]
        #get feature
        # features = extract_features_multi_mel(y_wav, sr=sampling_rate, hop=hop, nffts=[1024,2048,4096], mel_dim=feature_size)
        blocks_reduced_classes = get_raw_binary_classes_reduced_tensors_from_level(notes, sequence_length, 5, bpm, sr, hop, receptive_field)

        # np.save(features_file,features)
        # np.save(blocks_reduced_file,blocks_reduced)
        np.save(blocks_reduced_classes_file,blocks_reduced_classes)
