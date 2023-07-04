def generator():
    yield 'a'
    yield 'b'

for x in generator():
    print(x)
