# Player Talks column for Football Manager 27 (BepInEx mod) – beta

Adds a **Talks** column to your squad tables. Each row gets eight small buttons that open a player conversation
in one click, instead of right-click › Interaction › Praise › …

| Buttons | Meaning |
|---|---|
| green **F L V T** | praise **F**orm · **L**ast match performance · beha**V**iour (conduct) · **T**raining/development |
| red **F L V T** | criticise the same four topics |

Buttons the game does not offer right now (for example because you recently had that talk) turn grey.
The column only appears in tables with players of your own club. Scouting, the player database and
other clubs' squads are left alone.

The conversation itself opens as usual. You still pick the tone and the answers in the game.

## Requirements

- Football Manager 27 (PC, Steam). Tested on game build `6AFF57A2-1849A000`.
- [BepInEx 6 for Unity IL2CPP](https://builds.bepinex.dev/projects/bepinex_be) (tested with `6.0.0-be.755`),
  installed into the Football Manager 27 folder.

## Install

1. Install BepInEx 6 (IL2CPP) into `...\steamapps\common\Football Manager 27\` and start the game once,
   so BepInEx can generate its files.
2. Copy the `GespraechMod` folder (containing `GespraechMod.dll`) to
   `Football Manager 27\BepInEx\plugins\`.
3. Start the game.

**Back up your save before first use.** This is an unofficial mod.

## Use

1. Open your squad screen and **right-click any player once** after starting the game.
   This makes the game's menu system known to the mod. Until then no column appears.
2. The Talks column appears after a moment. While the mod is still checking which talks are available,
   the buttons are semi-transparent.
3. Click a button to open that conversation.

| Key | Action |
|---|---|
| F5 | show/hide the column |
| F4 | move the column: after "Player" / far left / far right |

You can't drag the column like the game's own columns, because it is not part of the game's column manager.

## Settings

`Football Manager 27\BepInEx\config\fm27assistant.gespraech.cfg` (created on first start):

| Setting | Default | |
|---|---|---|
| `Knoepfe` | true | column on/off (F5 saves here) |
| `SpaltenStellung` | 0 | 0 = after Player, 1 = far left, 2 = far right (F4 saves here) |
| `SpaltenBreite`, `KnopfGroesse` | 150, 16 | column width and button size in px |
| `VerfuegbarkeitPruefen` | true | grey out talks that are not offered (reads each row's menu in the background) |
| `ImSpielAusblenden` | true | hide the column during matches (no background checks either) |
| `NurTabellen` | playertable | only tables with these element names get the column (comma-separated, empty = all; names are written to the BepInEx log) |
| `Gelernt`, `LeistungStichworte` | | see "Languages" below |

## Languages

The mod recognises the talk entries by the game's internal action IDs, not by their text, so it should work
in any game language. One exception: "Form" and "Last match performance" share the same action ID.

- When both are in the menu, the mod tells them apart by their order and learns the texts of your language
  (stored in `Gelernt`).
- When only one of them is offered, the mod uses the learned text. If nothing has been learned yet, it uses the
  keywords in `LeistungStichworte` (German and English included). Add a keyword from your language if needed.

The tooltips show the menu texts of your game language once a menu has been read.

So far the mod has only been tested with the German game.

## Known limitations

- One right-click is needed after each game start.
- Tested on a single PC (one resolution, one UI scaling) and only in the squad views.
- A game update can change the game's menus or internals and break the mod.
- While the mod checks rows in the background, it opens their menus invisibly, one row at a time.
  Your own right-click always takes priority.

## Uninstall

Delete `BepInEx\plugins\GespraechMod\`. Optionally also delete `BepInEx\config\fm27assistant.gespraech.cfg`.

## Build from source

Requires the .NET SDK (6 or newer). References are taken from your game folder:

```
dotnet build -c Release -p:FM27Dir="C:\...\Football Manager 27" -p:Installieren=true
```

`-p:Installieren=true` copies the DLL into `BepInEx\plugins\GespraechMod\`. If the game is running, the loaded DLL
is renamed to `.alt` and the new one takes effect on the next start.

---

## Deutsch (Kurzfassung)

Fügt in den Kadertabellen eine Spalte **Gespräche** ein. Je Spieler gibt es Lob (grün) und Kritik (rot) zu
**F**orm, **L**eistung im letzten Spiel, **V**erhalten und **T**raining/Entwicklung. Ein Klick öffnet das Gespräch.
Gespräche, die das Spiel gerade nicht anbietet, sind grau.

- **Voraussetzung:** BepInEx 6 (IL2CPP) im FM27-Ordner.
- **Installation:** den Ordner `GespraechMod` nach `BepInEx\plugins\` kopieren.
- **Erster Start:** Nach jedem Spielstart einmal einen Spieler rechtsklicken.
- **Tasten:** F5 blendet die Spalte ein und aus, F4 wechselt ihre Position.
- **Vorher:** Spielstand sichern, der Mod ist inoffiziell und eine Beta.
