# Timeline-FindFourAI
An intelligent, human like AI will be present in the Four lounge, with whom you can play matches.

# Usage
Go to the Four Lounge, type in the chat `!Find4 [Difficulty Level]`. The bot will make you both join an available four board, and start the game!

Eg: `!Find4`, `!Find4 2`, `!Find4 3`

# Setup
To use this bot you are required to place the file `dassets.swf` in your `client` folder in your media server. ie,

Go to `media1/play/v2/client` and place the file `dassets.swf` in there.

Next, open `dependencies.json` in a text editor, and make changes as follows,

Find the following piece of code
```json
{
  "id": "interface",
  "title": "Interface"
},
```

Below that (after the `},`) add the following piece of code
```json
{
   "id": "dassets",
   "title": "Dote's Assets"
},
```

Save the file.

Next, you have to place the file `FindFourAI.py` in `Timeline/Plugins/` of your [Timeline](https://github.com/Times-0/Timeline) server and restart the server.

# Note
This plugin depends on pre-existing `Commands` plugin, by any change you choose to remove that plugin please don't.
