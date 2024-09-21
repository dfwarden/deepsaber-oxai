#!/usr/bin/env bash

# This script looks for the extracted Unity assets of Beat Saber in a folder
# dumped via AssetRipper, and copies/extracts all data into 
# data/extracted_data/official_beatsaber.

# make sure we have yq and jq
type yq
if [ $? -ne 0 ]; then
    echo "yq not found, it must be in \$PATH. Exiting..."
    exit
fi
type jq
if [ $? -ne 0 ]; then
    echo "jq not found, it must be in \$PATH. Exiting..."
    exit
fi


ASSETSDIR="/home/dfwarden/home-win/Desktop/test/ExportedProject/Assets"
OUT_DIR="$(dirname $( realpath ${BASH_SOURCE[0]} ))/../../../data/extracted_data/official_beatsaber"
mkdir -p $OUT_DIR

# official indexed difficulties 0-4 and their counterpart names
difficulties=(Easy Normal Hard Expert ExpertPlus)

# skip Metoronome, ArtTeam,Performance Test
for song_yaml in `ls $ASSETSDIR/MonoBehaviour/*BeatmapLevelData.asset | grep -vE "(Metronome|(ArtTeam|Performance)Test)BeatmapLevelData.asset$"`; do
    echo >&2 "found song yaml file $song_yaml";
    # remove every block of '/', and 'not-/' followed by '/', then remove trailing 'BeatmapLevelData.asset'
    song_title=$(echo $song_yaml | sed -E -e 's/^\/([^/]+\/)+//' -e 's/BeatmapLevelData.asset//')
    echo >&2 "parsed song title $song_title";

    # create/touch the folder for this song
    mkdir -p "${OUT_DIR}/${song_title}"

    # write out the song beatmap info json and BPM to info.dat
    yq . "${song_yaml:0:-10}.asset" >"${OUT_DIR}/${song_title}/${song_title}.info.json"
    yq '{_beatsPerMinute: .MonoBehaviour._beatsPerMinute}' "${song_yaml:0:-10}.asset" >"${OUT_DIR}/${song_title}/info.dat"

    # find the guid of the ogg of this song in .MonoBehaviour._audioClip.guid,
    # locate it in ASSETDIR/AudioClip, copy and rename it.
    song_ogg_guid=$(yq -r '.MonoBehaviour._audioClip.guid' $song_yaml)
    #echo >&2 "found song $song_title ogg guid $song_ogg_guid"
    song_ogg_meta=$(grep -l "${song_ogg_guid}" $ASSETSDIR/AudioClip/*ogg.meta)
    #echo >&2 "found song $song_title ogg meta $song_ogg_meta using guid $song_ogg_guid"
    # use Bash parameter expansion to slice off .meta, rename .ogg to .egg
    cp ${song_ogg_meta:0:-5} "${OUT_DIR}/${song_title}/${song_title}.egg"
    echo >&2 "Copied ${song_ogg_meta:0:-5} to ${OUT_DIR}/${song_title}/${song_title}.egg"

    # find the guid of the TextAsset file with the info about this song .ogg
    song_info_guid=$(yq -r '.MonoBehaviour._audioDataAsset.guid' $song_yaml)
    #echo >&2 "found song $song_title info guid $song_info_guid"
    song_info_meta=$(grep -l "${song_info_guid}" $ASSETSDIR/TextAsset/*audio.gz.bytes.meta)
    #echo >&2 "found song $song_title info meta $song_info_meta using guid $song_info_guid"
    # gunzip song info json bytes and run through jq
    gzip -dc ${song_info_meta:0:-5} | jq . >"${OUT_DIR}/${song_title}/${song_title}.audio.json"
    echo >&2 "Copied ${song_info_meta:0:-5} to ${OUT_DIR}/${song_title}/${song_title}.audio.json"

    # enumerate "Standard" difficulty set for this song, converting each difficulty file json to .dat
    # Indicies to this array ([0-4]) match $difficulties
    # Example from 100Bills:
    # 0 f179860377bc18846b26d7ab38f95a8a
    # 1 1932b706a6ebf7746a30f1984b868a20
    # Beware - filenames are wonky: TextAsset/Easy.beatmap.gz_3.bytes.meta for song Damage
    beatmaps_guids_str=$( yq -r '.MonoBehaviour._difficultyBeatmapSets[] | 
            select(._beatmapCharacteristicSerializedName == "Standard") | ._difficultyBeatmaps[] | 
            "\(._difficulty) \(._beatmapAsset.guid)"' \
            $song_yaml )
    while read difficulty_index beatmap_guid; do
        #echo >&2 "found song $song_title mode Standard beatmap file difficulty ${difficulties[$difficulty_index]} guid $beatmap_guid";
        beatmap_meta=$(grep -l "${beatmap_guid}" $ASSETSDIR/TextAsset/*.beatmap.gz*.bytes.meta)
        #echo >&2 "found song $song_title move Standard beatmap file difficulty ${difficulties[$difficulty_index]} meta $beatmap_meta using guid $beatmap_guid"
        gzip -dc ${beatmap_meta:0:-5} | jq . >"${OUT_DIR}/${song_title}/${difficulties[$difficulty_index]}.dat"
        echo >&2 "Copied ${beatmap_meta:0:-5} to ${OUT_DIR}/${song_title}/${difficulties[$difficulty_index]}.dat"
    # FYI: below is Bash's "Here Strings", couldn't find a more obvious way of doing this
    done <<<$beatmaps_guids_str
done