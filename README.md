# SC2 Replay data dump

Small utility tool around [s2protocol](https://github.com/Blizzard/s2protocol) for processing `.SC2Replay` files. At the time being it exposes just two functionalities that might come useful for modders... and not only.

* Prints players list. including `PlayerHandle`
* Reconstruction of every `*.SC2Bank` file. Data comes from _NNet_ packets that is transmitted during preload process of online game.

## Installation

### Method 1 - Manual

**Requirements**

* Python2 (yes - **v2**, because _s2protocol_ is not compatible with py3...)

**Installation**

```sh
pip2 install https://github.com/Talv/sc2-repdump/archive/master.zip
```

### Method 2 - Bundled exe

Don't want to bother with installing Python environment? That's fine, you can download bundled version of this script, with single executable for Windows from [releases](https://github.com/Talv/sc2-repdump/releases).

## Usage

It's command line tool.

```
usage: s2repdump [-h] [--players] [--bank BANK] [--out OUT] [replay_file]

: Dump player handles:
 --players [replay_file]

: Reconstruct players .SC2Bank files
 --bank [player_slot] [replay_file]


positional arguments:
  replay_file  .SC2Replay file to load

optional arguments:
  -h, --help   show this help message and exit
  --players    print info about players
  --bank BANK  reconstruct player's SC2Bank files
  --out OUT    output directory
```

## Examples

**Dump list of the players**

It includes zero-indexed slotid, that should be used for `--bank` parameter.

```sh
$ s2repdump somerandomreplay.SC2Replay --players
{
 "0": {
  "handle": "2-S2-1-2642502",
  "name": "Talv"
 }
}
```

**Reconstruct `.SC2Bank` files of player at slot provided**

```sh
$ s2repdump somerandomreplay.SC2Replay --bank 0
Processing player "Talv"
Reconstructed "sefibecvprofile.SC2Bank"
Reconstructed "sefibeoptions.SC2Bank"
Reconstructed "sefiberewards.SC2Bank"
```
