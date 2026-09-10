"""Winx Club canon: characters, realms and the Season 1 story.

Everything narrative lives here so the level code stays about geometry.  The
campaign follows the first season's arc: Bloom's discovery on Earth, Alfea,
the Trix's hunt for the four pieces of the Codex, and the siege of Alfea.

Names, places and powers follow the original series (the RAI/4Kids Season 1);
where the two dubs differ the original name is used with the dub name noted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from panda3d.core import Vec4


# ---------------------------------------------------------------------------
# Realms
# ---------------------------------------------------------------------------
REALMS = {
    "earth": "Earth - Gardenia",
    "magix": "Magix",
    "domino": "Domino",           # 'Sparx' in the 4Kids dub
    "solaria": "Solaria",
    "lynphea": "Lynphea",
    "melody": "Melody",
    "zenith": "Zenith",
    "andros": "Andros",
}


# ---------------------------------------------------------------------------
# Speakers - anyone who gets a line, with the colour their name is drawn in
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Speaker:
    key: str
    name: str
    title: str
    color: Vec4


SPEAKERS = {s.key: s for s in [
    Speaker("narrator", "", "", Vec4(0.80, 0.84, 0.95, 1)),
    # --- The Winx ---------------------------------------------------------
    Speaker("bloom", "Bloom", "Fairy of the Dragon Flame",
            Vec4(1.00, 0.55, 0.30, 1)),
    Speaker("stella", "Stella", "Fairy of the Shining Sun",
            Vec4(1.00, 0.85, 0.35, 1)),
    Speaker("flora", "Flora", "Fairy of Nature", Vec4(0.55, 0.90, 0.55, 1)),
    Speaker("musa", "Musa", "Fairy of Music", Vec4(0.95, 0.45, 0.65, 1)),
    Speaker("tecna", "Tecna", "Fairy of Technology",
            Vec4(0.45, 0.92, 0.90, 1)),
    Speaker("aisha", "Aisha", "Fairy of Waves", Vec4(0.45, 0.75, 1.00, 1)),
    # --- Alfea ------------------------------------------------------------
    Speaker("faragonda", "Faragonda", "Headmistress of Alfea",
            Vec4(0.85, 0.80, 1.00, 1)),
    Speaker("griselda", "Griselda", "Head of Discipline",
            Vec4(0.75, 0.75, 0.85, 1)),
    # --- Cloud Tower ------------------------------------------------------
    Speaker("griffin", "Griffin", "Headmistress of Cloud Tower",
            Vec4(0.70, 0.55, 0.90, 1)),
    # --- Red Fountain -----------------------------------------------------
    Speaker("saladin", "Saladin", "Headmaster of Red Fountain",
            Vec4(0.90, 0.75, 0.55, 1)),
    Speaker("sky", "Sky", "Prince of Eraklyon", Vec4(0.60, 0.80, 1.00, 1)),
    Speaker("brandon", "Brandon", "Specialist", Vec4(0.70, 0.90, 0.70, 1)),
    Speaker("riven", "Riven", "Specialist", Vec4(0.95, 0.50, 0.50, 1)),
    Speaker("timmy", "Timmy", "Specialist", Vec4(0.85, 0.85, 0.60, 1)),
    # --- The Trix and their servants --------------------------------------
    Speaker("icy", "Icy", "Witch of Ice", Vec4(0.70, 0.92, 1.00, 1)),
    Speaker("darcy", "Darcy", "Witch of Darkness", Vec4(0.72, 0.55, 0.95, 1)),
    Speaker("stormy", "Stormy", "Witch of Storms", Vec4(0.95, 0.55, 0.85, 1)),
    Speaker("knut", "Knut", "Ogre", Vec4(0.80, 0.65, 0.45, 1)),
    # --- Domino -----------------------------------------------------------
    Speaker("daphne", "Daphne", "Nymph of Domino",
            Vec4(0.95, 0.90, 0.70, 1)),
]}


# ---------------------------------------------------------------------------
# The Codex
# ---------------------------------------------------------------------------
# In Season 1 the Trix hunt four pieces of the Codex, one kept by each of the
# three schools and one by the pixies.  Together they open the way to the
# Realix dimension and its Ultimate Power.
CODEX_PIECES = ("Alfea", "Cloud Tower", "Red Fountain", "Pixie Village")


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------
@dataclass
class Chapter:
    """The story wrapped around one level."""
    number: int
    title: str
    realm: str
    intro: list = field(default_factory=list)    # [(speaker_key, line), ...]
    outro: list = field(default_factory=list)
    objective: str = ""
    codex: str = ""        # which Codex piece this chapter concerns, if any


CHAPTERS = {

    # --- Chapter 1 is Bloom's; the other fairies get their own realm below --
    "home_bloom": Chapter(
        1, "The Ogre in the Park", "earth",
        objective="Drive Knut and his ghouls out of Gardenia Park.",
        intro=[
            ("narrator", "Gardenia. A quiet town on Earth, where nothing "
                         "magical has ever happened."),
            ("narrator", "Bloom is sixteen, lives above her mother's flower "
                         "shop, and is about to have a very strange afternoon."),
            ("stella", "Behind you! Get down!"),
            ("bloom", "That is an ogre. There is an ogre in the park."),
            ("knut", "Hand over the Ring of Solaria, princess, and nobody "
                     "gets stepped on."),
            ("stella", "You felt that, didn't you? That spark. You have "
                       "magic - so use it!"),
        ],
        outro=[
            ("stella", "I have never seen a first transformation like that. "
                       "What realm are you from?"),
            ("bloom", "...Gardenia?"),
            ("stella", "Right. Pack a bag. You are coming to Alfea."),
        ]),

    "alfea": Chapter(
        2, "College for Fairies", "magix",
        objective="Pass Griselda's field exercise - and whatever crashes it.",
        codex="Alfea",
        intro=[
            ("narrator", "Magix. A realm where the three schools sit within "
                         "a day's ride of one another, and rarely get along."),
            ("faragonda", "Welcome to Alfea. You arrive as girls with a "
                          "talent. You will leave as guardian fairies."),
            ("griselda", "There are rules. There are a great many rules. "
                         "You will meet me every time you break one."),
            ("flora", "I am Flora. That is Musa, and Tecna. We are your "
                      "suitemates - so I hope you like company."),
            ("griselda", "Courtyard. Now. Field exercise."),
            ("tecna", "Headmistress - my scanner is reading something in the "
                      "courtyard that is not a student."),
        ],
        outro=[
            ("faragonda", "Ghouls. Inside the barrier, in daylight."),
            ("griselda", "Somebody sent them. Ghouls do not wander."),
            ("faragonda", "Say nothing to the students yet. And Bloom - stay "
                          "close to the school."),
        ]),

    "swamp": Chapter(
        3, "Black Mud Swamp", "magix",
        objective="Find Knut's hideout and learn who he answers to.",
        intro=[
            ("musa", "Follow the smell, she says. Great plan, Stella."),
            ("stella", "Ogres are not subtle. Neither is that hut."),
            ("knut", "You should not have come out here, fairies."),
            ("icy", "No. They really should not have."),
            ("darcy", "Three witches of Cloud Tower, little fairy. Icy. "
                      "Darcy. Stormy."),
            ("stormy", "The Trix. Remember it - you will be hearing it a lot."),
        ],
        outro=[
            ("icy", "She has it. Did you feel that? Inside the redhead."),
            ("darcy", "The Dragon Flame. After all this time, and it is "
                      "walking around in a first-year."),
            ("icy", "Then we take it. And everything it opens."),
        ]),

    "cloudtower": Chapter(
        4, "The Book of Fate", "magix",
        objective="Reach the Book of Fate before the Trix do.",
        codex="Cloud Tower",
        intro=[
            ("tecna", "Cloud Tower. The corridors rearrange themselves. I "
                      "have mapped it four times and been wrong four times."),
            ("bloom", "The Book of Fate has an entry on every witch and every "
                      "fairy. If the Trix know what I am, it will say why."),
            ("griffin", "My school. My book. And three of my students who "
                        "have not attended a lesson in weeks."),
            ("darcy", "Too late, fairy. We have read your page."),
        ],
        outro=[
            ("griffin", "Domino. The realm that burned. You are asking about "
                        "Domino."),
            ("bloom", "You know something about me."),
            ("griffin", "I know enough to tell you to go to Lake Roccaluce, "
                        "and to be careful what answers you ask for."),
        ]),

    "roccaluce": Chapter(
        5, "Lake Roccaluce", "magix",
        objective="Reach the heart of the lake. Survive what follows.",
        intro=[
            ("narrator", "Lake Roccaluce. Cold enough in summer to keep most "
                         "people away, which is rather the point."),
            ("daphne", "Bloom. I have waited a long while to say your name "
                       "out loud."),
            ("bloom", "You know me?"),
            ("daphne", "I am Daphne, Nymph of Domino. Your sister. Domino "
                       "fell to the Ancestral Witches, and I carried you to "
                       "Earth with the last of the Dragon Flame inside you."),
            ("icy", "How touching. And how convenient - both of you in one "
                    "place."),
        ],
        outro=[
            ("bloom", "Domino. Oritel and Marion. I had a family and a realm "
                      "and I never knew."),
            ("daphne", "You have them still. But the Flame you carry is the "
                       "last of the Great Dragon, and the Trix will not stop."),
        ]),

    "redfountain": Chapter(
        6, "Red Fountain", "magix",
        objective="Hold Red Fountain. Do not let them take the Codex.",
        codex="Red Fountain",
        intro=[
            ("saladin", "Red Fountain. School of Heroics and Bravery. Today, "
                        "apparently, of emergencies."),
            ("sky", "They came straight over the wall. They knew exactly "
                    "where the vault was."),
            ("brandon", "Riven let them in. He has been at Cloud Tower for "
                        "weeks and he will not say why."),
            ("stormy", "Because I asked nicely. Now stand still while I bring "
                       "the roof down."),
        ],
        outro=[
            ("saladin", "Two pieces of the Codex gone. Alfea's and ours."),
            ("faragonda", "Four pieces open the way to Realix, Saladin. And "
                          "they have half of them."),
            ("tecna", "Then the remaining two are Cloud Tower's - and the "
                      "pixies'."),
        ]),

    "pixievillage": Chapter(
        7, "Pixie Village", "magix",
        objective="Get the pixies out and the last Codex piece with them.",
        codex="Pixie Village",
        intro=[
            ("flora", "It is so small. They built all of this themselves."),
            ("narrator", "The pixies have guarded their piece of the Codex "
                         "since long before Alfea had a headmistress."),
            ("darcy", "Hello, little things. We are here for the shiny one."),
            ("musa", "You will have to go through us."),
            ("darcy", "Yes. That is rather the fun part."),
        ],
        outro=[
            ("stella", "We saved the pixies. We did not save the Codex."),
            ("faragonda", "All four pieces. They can open Realix and take the "
                          "Ultimate Power for themselves."),
            ("bloom", "Then we stop them at Cloud Tower. Tonight."),
        ]),

    "siege_cloudtower": Chapter(
        9, "Cloud Tower Has Fallen", "magix",
        objective="Cut through the Army of Decay and reach Darcy.",
        intro=[
            ("griffin", "They took my school in a single night. My witches "
                        "are locked in their own dormitories."),
            ("narrator", "The Trix opened Realix and drew out the Ultimate "
                         "Power: the Army of Decay - which rots whatever it "
                         "touches, and cannot be killed by ordinary magic."),
            ("icy", "You are standing in my school now, fairy."),
            ("griffin", "It was never yours, Icy. You were failing my second "
                        "year when you walked out of it."),
        ],
        outro=[
            ("griffin", "Go. Alfea is next and they will not wait for you."),
            ("bloom", "Come with us."),
            ("griffin", "I have three hundred witches behind a locked door. "
                        "I will bring them. Hold your school until I do."),
        ]),

    "battle_alfea": Chapter(
        10, "The Battle of Alfea", "magix",
        objective="Hold the courtyard, then finish the Trix.",
        intro=[
            ("narrator", "The Army of Decay reached Alfea's barrier at dawn "
                         "and went straight through it."),
            ("faragonda", "Every student to the courtyard. Nobody fights "
                          "alone today."),
            ("icy", "Give us the Dragon Flame, Bloom, and we will leave one "
                    "wall standing."),
            ("bloom", "You have spent all season chasing this thing."),
            ("bloom", "You never once asked whether I had learned to use it."),
        ],
        outro=[
            ("narrator", "The Army of Decay came apart the moment the Trix "
                         "lost hold of it."),
            ("faragonda", "The Trix will be sealed where they can do no more "
                          "harm. And Alfea still stands."),
            ("daphne", "The last of the Great Dragon burns in you, sister. "
                       "Domino is not gone while you remember it."),
            ("narrator", "First year: complete."),
        ]),
}


# ---------------------------------------------------------------------------
# Home realms - chapters 1 and 8 change with the fairy you picked
# ---------------------------------------------------------------------------
# Each fairy opens the game in her own realm and returns to it later, once the
# Trix have the Codex and start striking the realms directly.
HOME_CHAPTERS = {

    "stella": (Chapter(
        1, "The Ring of Solaria", "solaria",
        objective="Clear the palace grounds. Try not to break anything else.",
        intro=[
            ("narrator", "Solaria. A realm with two suns and no night worth "
                         "the name."),
            ("stella", "One year at Alfea and I set the potions lab on fire. "
                       "Father is thrilled."),
            ("knut", "The Ring of Solaria. Hand it over."),
            ("stella", "An ogre. In the palace. Somebody is going to hear "
                       "about this."),
        ],
        outro=[
            ("stella", "He was not here for me. He was here for the ring."),
            ("narrator", "Someone had sent an ogre across realms for a single "
                         "piece of jewellery. Stella went back to Alfea early."),
        ]),
        Chapter(
        8, "The Sun Goes Out", "solaria",
        objective="Get the palace clear before the Decay reaches the city.",
        intro=[
            ("stella", "They put out the suns. Both of them."),
            ("stormy", "Do you like it? Your realm looks so much better in "
                       "the dark."),
            ("stella", "That is my home you are standing on."),
        ],
        outro=[
            ("stella", "Solaria will hold. It is going to take years, but it "
                       "will hold."),
            ("faragonda", "They are striking the realms one at a time to keep "
                          "us scattered. Come back to Alfea."),
        ])),

    "flora": (Chapter(
        1, "Roots and Thorns", "lynphea",
        objective="Drive them out of the grove before they reach the heartwood.",
        intro=[
            ("narrator", "Lynphea. Everything here grew past the scale it was "
                         "meant to, and then kept going."),
            ("flora", "The grove is frightened. I can hear it from here."),
            ("knut", "Out of the way, flower girl."),
            ("flora", "No. You are standing on something three thousand years "
                      "old."),
        ],
        outro=[
            ("flora", "He was digging. Looking for something under the roots."),
            ("narrator", "Lynphea sent its quietest daughter to Alfea to find "
                         "out what."),
        ]),
        Chapter(
        8, "The Blight", "lynphea",
        objective="Burn the rot out of the grove. Save the heartwood.",
        intro=[
            ("flora", "The Army of Decay does not kill things. It makes them "
                      "rot while they are still alive."),
            ("darcy", "Your whole realm is a garden, Flora. Gardens die."),
            ("flora", "Not this one. Not today."),
        ],
        outro=[
            ("flora", "The heartwood held. Everything else will grow back "
                      "from it."),
            ("faragonda", "They are hitting the realms one at a time. Come "
                          "back to Alfea, Flora."),
        ])),

    "musa": (Chapter(
        1, "The Silent Valley", "melody",
        objective="Clear the amphitheatre. Melody does not do quiet.",
        intro=[
            ("narrator", "Melody. A valley built to be played - drums, "
                         "strings, and a wind that carries for miles."),
            ("musa", "It is silent. This valley has never once been silent."),
            ("knut", "Nobody left to hear you scream, then."),
            ("musa", "Wrong. Everybody is going to hear this."),
        ],
        outro=[
            ("musa", "Ogres do not walk into Melody on their own."),
            ("narrator", "She left for Alfea the same week, and did not say "
                         "goodbye to anyone."),
        ]),
        Chapter(
        8, "Every String Cut", "melody",
        objective="Take the valley back, one stage at a time.",
        intro=[
            ("musa", "They cut every string in the valley. Every single one."),
            ("icy", "It was giving me a headache."),
            ("musa", "You have no idea what you just took from me."),
        ],
        outro=[
            ("musa", "It will play again. It takes more than three witches to "
                     "shut this valley up."),
            ("faragonda", "One realm at a time, to keep us apart. Come home to "
                          "Alfea."),
        ])),

    "tecna": (Chapter(
        1, "System Fault", "zenith",
        objective="Trace the intrusion to its source and remove it.",
        intro=[
            ("narrator", "Zenith. Everything measured, everything on a grid, "
                         "nothing left to chance."),
            ("tecna", "An unlogged intrusion. On Zenith that is not a fault, "
                      "it is an impossibility."),
            ("knut", "Stop making that noise and stand still."),
            ("tecna", "Fascinating. An ogre that has defeated a realm-wide "
                      "sensor grid. That should not be possible either."),
        ],
        outro=[
            ("tecna", "Someone routed him past every sensor we have. Someone "
                      "with resources."),
            ("narrator", "Zenith does not like unsolved problems. It sent one "
                         "of its best to Alfea to solve this one."),
        ]),
        Chapter(
        8, "All Systems Red", "zenith",
        objective="Restore the core before the realm goes dark.",
        intro=[
            ("tecna", "Every indicator in the realm is reading red. That is "
                      "not an alarm state - there is no state past this one."),
            ("darcy", "I do love a realm that tells you exactly how badly it "
                      "is doing."),
            ("tecna", "Then let me be precise: you are outnumbered."),
        ],
        outro=[
            ("tecna", "Core stable. Losses recoverable. Barely."),
            ("faragonda", "They are picking off the realms in sequence. Come "
                          "back to Alfea."),
        ])),

    "aisha": (Chapter(
        1, "The Tide Turns", "andros",
        objective="Clear the causeways and get the city sealed.",
        intro=[
            ("narrator", "Andros. Nine tenths water, and the tenth that is "
                         "not is mostly bridges."),
            ("aisha", "Something came out of the deep water last night."),
            ("knut", "Little princess. All alone on a very long bridge."),
            ("aisha", "You picked the wrong realm to fight on."),
        ],
        outro=[
            ("aisha", "It came from outside Andros. Somebody sent it."),
            ("narrator", "Andros sent its princess to Alfea to find out who."),
        ]),
        Chapter(
        8, "Poisoned Water", "andros",
        objective="Clear the sea before the rot reaches the city.",
        intro=[
            ("aisha", "They put the Army of Decay in the water. In the water."),
            ("icy", "It spreads so nicely that way. Everything here is "
                    "connected."),
            ("aisha", "Then so am I. To all of it."),
        ],
        outro=[
            ("aisha", "The tide will carry the rest of it out. Andros holds."),
            ("faragonda", "Realm by realm, to keep us scattered. Come back to "
                          "Alfea."),
        ])),
}

# Bloom's home chapters are the Gardenia ones defined above, plus this siege.
CHAPTERS["siege_bloom"] = Chapter(
    8, "They Followed You Home", "earth",
    objective="Get Gardenia clear. Nobody here can fight this.",
    intro=[
        ("narrator", "Gardenia. No barrier, no fairies, no idea what is "
                     "coming down the street."),
        ("bloom", "This is where I grew up. There are people asleep in those "
                  "houses."),
        ("stormy", "Then wake them up. I want an audience."),
    ],
    outro=[
        ("bloom", "They came here because of me."),
        ("faragonda", "They came because they are taking the realms one at a "
                      "time. Gardenia was simply first. Come back to Alfea."),
    ])

HOME_CHAPTERS["bloom"] = (CHAPTERS["home_bloom"], CHAPTERS["siege_bloom"])
for _key, (_calm, _siege) in HOME_CHAPTERS.items():
    CHAPTERS.setdefault("home_" + _key, _calm)
    CHAPTERS.setdefault("siege_" + _key, _siege)


# The shared chapters, in the order they are played.  Slots 1 and 8 come from
# HOME_CHAPTERS and depend on the chosen fairy.
CAMPAIGN_TEMPLATE = ["home", "alfea", "swamp", "cloudtower", "roccaluce",
                     "redfountain", "pixievillage", "siege",
                     "siege_cloudtower", "battle_alfea"]


def campaign_keys(fairy_key: str) -> list:
    """Level/chapter keys for this fairy's run, in order."""
    return [("home_" + fairy_key) if s == "home" else
            ("siege_" + fairy_key) if s == "siege" else s
            for s in CAMPAIGN_TEMPLATE]


def chapter_for(level_key: str) -> Chapter | None:
    return CHAPTERS.get(level_key)


def speaker(key: str) -> Speaker:
    return SPEAKERS.get(key, SPEAKERS["narrator"])
