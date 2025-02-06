import subprocess


def send(Title, Message, Icon="dialog-information", Timeout="5000"):
    subprocess.run(
        ["notify-send", "-i", Icon, "-t", Timeout, Title, Message],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
