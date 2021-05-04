# SC2 Replay data dump

Small utility tool around [s2protocol](https://github.com/Blizzard/s2protocol) for processing `.SC2Replay` files. At the time being it exposes just few functionalities that might come useful to modders... and not only.

* Listing players and their properties, including `PlayerHandle`
* Listing and reconstruction of every `*.SC2Bank` file. (Data comes from preload section which takes place before game begins).
* Chatlog

## Installation

**Requirements**

* Python3

**Installation**

```sh
pip install https://github.com/Talv/sc2-repdump/archive/master.zip
```

## Usage

It's command line tool.

```
usage: s2repdump [-h] [-v] [-q] [-V] [-j] [-J] [-O OUT] [-f] [--strict] [-d {info,players,chat,banks}] [-R]
                 replay_file

positional arguments:
  replay_file           .SC2Replay file to load

optional arguments:
  -h, --help            show this help message and exit

common:
  -v, --verbose         verbose logging; stacks up to 3
  -q, --quiet
  -V, --version         show program's version number and exit
  -j, --json            output data as JSON
  -J, --json-compact    output data as compact JSON
  -O OUT, --out OUT     output directory
  -f, --force           force certain operations that otherwise would've been aborted - such overwriting existing files
  --strict              do not try to decode replays if there's not matching protocol

actions:
  -d {info,players,chat,banks}, --decode {info,players,chat,banks}
                        decode and output specified data section
  -R, --bank-rebuild    rebuild SC2Bank files
```

## Examples

**Dump list of the players**

```js
$ s2repdump -d players -d banks --bank-list IBE2.SC2Replay

## PLAYERS

|   idx |   pid |   uid | name         | clan   | ctrl   | toon           |   working_slot | color      |
|-------|-------|-------|--------------|--------|--------|----------------|----------------|------------|
|     1 |     1 |     0 | Aduolu       | <lCED> | HUMAN  | 2-S2-1-1439099 |              0 | Yellow     |
|     2 |     2 |     1 | LaZator      | <lCED> | HUMAN  | 2-S2-1-6903403 |              1 | Teal       |
|     3 |     3 |     2 | lethern      |        | HUMAN  | 2-S2-1-4621295 |              2 | #FF0000    |
|     4 |     4 |     3 | Talv         |        | HUMAN  | 2-S2-1-2642502 |              3 | Green      |
|     5 |     5 |     4 | Adimax       |        | HUMAN  | 2-S2-1-430056  |              4 | Orange     |
|     6 |     6 |     5 | Slavez       |        | HUMAN  | 2-S2-1-7547579 |              5 | Light Grey |
|     7 |     7 |     6 | abdol        |        | HUMAN  | 2-S2-1-7231207 |              6 | Pink       |
|     8 |     8 |     7 | Joakinho     | <IBǤŘ> | HUMAN  | 2-S2-1-2953237 |              7 | Violet     |
|     9 |     9 |     8 | DruNkenPandA | <lCED> | HUMAN  | 2-S2-1-1908845 |              8 | Dark Grey  |


## BANKS

|   idx |   uid | player       | name           |   net_size |   content_size |   sections_count |   keys_count | signed   |
|-------|-------|--------------|----------------|------------|----------------|------------------|--------------|----------|
|     0 |     0 | Aduolu       | IBE2statsBAK   |      49837 |          30483 |              157 |         1569 | True     |
|     1 |     0 | Aduolu       | IBEops         |        222 |            117 |                1 |            8 | False    |
|     2 |     0 | Aduolu       | IBE2stats      |      50042 |          30691 |              157 |         1569 | True     |
|     3 |     0 | Aduolu       | ZCampaignStats |      76358 |          58660 |               21 |         1063 | False    |
|     4 |     0 | Aduolu       | ZArchive       |         30 |              0 |                0 |            0 | False    |
|     5 |     1 | LaZator      | IBE2statsBAK   |      57521 |          37237 |              161 |         1609 | True     |
|     6 |     1 | LaZator      | IBEops         |        222 |            117 |                1 |            8 | False    |
|     7 |     1 | LaZator      | IBE2stats      |      57726 |          37445 |              161 |         1609 | True     |
|     8 |     2 | lethern      | IBE2stats      |      50840 |          33857 |              133 |         1329 | True     |
|     9 |     2 | lethern      | IBE2statsBAK   |      50758 |          33772 |              133 |         1329 | True     |
|    10 |     2 | lethern      | IBEops         |        222 |            117 |                1 |            8 | False    |
|    11 |     3 | Talv         | IBE2stats      |      74936 |          49295 |              201 |         2009 | True     |
|    12 |     3 | Talv         | IBE2statsBAK   |      74707 |          49063 |              201 |         2009 | True     |
|    13 |     3 | Talv         | IBEops         |        222 |            117 |                1 |            8 | False    |
|    14 |     4 | Adimax       | IBE2statsBAK   |      71766 |          46959 |              194 |         1939 | True     |
|    15 |     4 | Adimax       | IBEops         |        221 |            117 |                1 |            8 | False    |
|    16 |     4 | Adimax       | IBE2stats      |      71937 |          47133 |              194 |         1939 | True     |
|    17 |     5 | Slavez       | IBE2stats      |       1483 |            965 |                4 |           39 | True     |
|    18 |     5 | Slavez       | IBEops         |        222 |            117 |                1 |            8 | False    |
|    19 |     5 | Slavez       | IBE2statsBAK   |        981 |            587 |                3 |           29 | True     |
|    20 |     6 | abdol        | IBE2statsBAK   |      21044 |          13243 |               61 |          609 | True     |
|    21 |     6 | abdol        | IBEops         |        222 |            117 |                1 |            8 | False    |
|    22 |     6 | abdol        | IBE2stats      |      21041 |          13243 |               61 |          609 | True     |
|    23 |     7 | Joakinho     | IBE2statsBAK   |      58136 |          37807 |              159 |         1589 | True     |
|    24 |     7 | Joakinho     | IBE2stats      |      58211 |          37885 |              159 |         1589 | True     |
|    25 |     7 | Joakinho     | IBEops         |        222 |            117 |                1 |            8 | False    |
|    26 |     8 | DruNkenPandA | IBE2statsBAK   |      70038 |          44454 |              201 |         2009 | True     |
|    27 |     8 | DruNkenPandA | IBEops         |        222 |            117 |                1 |            8 | False    |
|    28 |     8 | DruNkenPandA | IBE2stats      |      69992 |          44411 |              201 |         2009 | True     |
```

**Reconstruct `.SC2Bank` files**

```js
$ s2repdump --bank-rebuild IBE2.SC2Replay
```

Result:

```js
$ exa -Th
.
├── IBE2.SC2Replay
└── out
   ├── 2-S2-1-430056
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-1439099
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  ├── IBEops.SC2Bank
   │  ├── ZArchive.SC2Bank
   │  └── ZCampaignStats.SC2Bank
   ├── 2-S2-1-1908845
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-2642502
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-2953237
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-4621295
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-6903403
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   ├── 2-S2-1-7231207
   │  ├── IBE2stats.SC2Bank
   │  ├── IBE2statsBAK.SC2Bank
   │  └── IBEops.SC2Bank
   └── 2-S2-1-7547579
      ├── IBE2stats.SC2Bank
      ├── IBE2statsBAK.SC2Bank
      └── IBEops.SC2Bank
```
