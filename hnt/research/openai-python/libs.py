from time import time

start = time()

# import requests # 0.11 on average
import httpx  # 0.065 on average
# import aiohttp # 0.17 on average

# collectively ~0.01 on average
# import os
# import json
# import sys

end = time()
print(end - start)
