from time import time

start = time()

from litellm import completion

end = time()
print(end - start)
