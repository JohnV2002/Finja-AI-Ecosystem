import random, string
token = ''.join(random.choice(string.ascii_letters) for _ in range(64))
print(token)
