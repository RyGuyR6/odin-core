class Odin:
    """
    The central application object.

    Every future system (GitHub, Memory, Discord, Minecraft, etc.)
    will be attached here.
    """

    def __init__(self):
        self.name = "Odin"
        self.version = "0.0.1"

    def status(self):
        return {
            "name": self.name,
            "version": self.version,
            "status": "online",
        }