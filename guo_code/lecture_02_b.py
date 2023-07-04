def f(x=5):
    def g(y=6):
        print(x + y)
    return g
