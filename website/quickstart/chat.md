# ChatGPT and other chats

A chat without tools can still write Shapewright sources well. It just cannot run them, so you run `sw`.

1. `pip install "git+https://github.com/billtruong003/shapewright"`, then `sw caps --llms > llms.txt`.
2. Paste `llms.txt` into the chat, then your request.
3. Save the YAML it writes as `assets/NAME/asset.yaml` and run `sw review NAME`.
4. Paste the validation output back and attach `assets/NAME/.build/sheet.png`. Most chats read images, so ask for a critique and a revision.
5. `sw export NAME --target godot` when it is right.

This is slower than an agent with tools (you are the tool runner), but the source it produces is the same format.
