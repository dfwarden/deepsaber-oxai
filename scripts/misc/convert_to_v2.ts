import * as bsmap from 'jsr:@kvl/bsmap'

import * as glob from 'glob'

const v4Files = glob.sync('data/extracted_data/official_beatsaber/*/*.v4')

for (const v4File of v4Files.slice(0)) {
    console.log(`processing ${v4File}`)

    const data = bsmap.readDifficultyFileSync(v4File)

    //console.log(`want to write to ${v4File.slice(0, -3)}`)
    // skip validation checks - some official songs are not technically v2 compatible
    // see https://github.com/KivalEvan/BeatSaber-JSMap/blob/f399d7a33ca356b0cf0102a1db082188a27be6eb/src/write/_main.ts
    bsmap.writeDifficultyFileSync(data, 2, {
        filename: v4File.slice(0, -3),
        save: {
            validate: {
                enabled: false,
            }
        }
    })
}