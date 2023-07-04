class IterateForever:
    def __init__(self, x_arg):
        self.x = x_arg

    def __next__(self):
        return self.x

iterate_forever = IterateForever(42)
