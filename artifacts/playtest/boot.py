"""Boot: title -> intro speech -> naming -> truck -> walk out of the truck.

The rule that keeps the field healthy: A is pressed freely while the game is
not yet in the field (title, movie, speech, naming), and never pressed once the
field is live unless a text box is actually waiting. Directions are the only
field input.
"""
import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, "artifacts/playtest")
import bot
from input import Field


def main():
    f = Field()
    transcript = []

    def say(line):
        print(line, flush=True)
        transcript.append(line)

    f.state("boot start")

    # 1. Everything before the field: A until the naming screen appears.
    for i in range(400):
        sc = f.scene().lower()
        if "naming" in sc:
            break
        if sc == "overworld":
            break
        f.a(26)
    say(f"pre-field loop end: scene={f.scene()}")

    # 2. Naming: Start jumps the cursor to OK, A accepts, then "is this OK?" = A.
    if "naming" in f.scene().lower():
        f.tap("start", 2, 3)
        f.frames(30)
        f.a(24)
        for _ in range(8):
            if "naming" not in f.scene().lower():
                break
            f.a(30)
        say(f"after naming: scene={f.scene()}")

    # 3. After naming comes "So it's NAME?" (a Yes/No menu) and Birch's
    #    send-off: A while a menu or a text box is waiting.
    for _ in range(120):
        if f.scene() == "overworld" and not f.box_open() and not f.status()["menu"]:
            break
        if f.status()["menu"] or f.box_open():
            f.a(24)
        else:
            f.frames(20)
    say(f"entered field: scene={f.scene()}")

    # 4. Do not touch A in the truck; let the opening script finish.
    for _ in range(90):
        if f.scene() == "overworld" and not f.busy():
            break
        f.frames(20)
    f.state("in field")

    # 5. Walk east out of the truck, directions only.
    for i in range(10):
        if f.scene() != "overworld":
            break
        if f.box_open():
            f.advance_text(4)
            continue
        before = f.nav()
        f.step("right", press=12, release=4)
        after = f.nav()
        say(f"  right#{i + 1}: ({before['x']},{before['y']}) -> ({after['x']},{after['y']}) "
            f"map {before['map']} -> {after['map']}")
        if after["map"] != before["map"]:
            break
        f.frames(10)

    # 6. Read out whatever the intro says now.
    for _ in range(40):
        if f.box_open():
            f.advance_text(3)
        else:
            f.frames(20)
    f.state("walk end")
    say("speech tail: " + " | ".join(f.speech()[-5:]))

    with open("artifacts/playtest/transcript-boot.txt", "w") as fh:
        fh.write("\n".join(transcript) + "\n\n--- spoken ---\n")
        fh.write("\n".join(f.speech()) + "\n")
    print("wrote artifacts/playtest/transcript-boot.txt", flush=True)
    print("stats:", f.stats, flush=True)


if __name__ == "__main__":
    main()
