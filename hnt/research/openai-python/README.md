# GNU time
```
$ env time sleep 1
0.00user 0.00system 0:01.00elapsed 0%CPU (0avgtext+0avgdata 3740maxresident)k
0inputs+0outputs (0major+87minor)pagefaults 0swaps
```

# uv python baseline timing
```
$ env time uv run empty.py
apple
0.01user 0.00system 0:00.02elapsed 96%CPU (0avgtext+0avgdata 42200maxresident)k
0inputs+0outputs (0major+2131minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.01system 0:00.02elapsed 96%CPU (0avgtext+0avgdata 41976maxresident)k
0inputs+0outputs (0major+2125minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.01system 0:00.02elapsed 93%CPU (0avgtext+0avgdata 42496maxresident)k
0inputs+0outputs (0major+2140minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.01system 0:00.02elapsed 92%CPU (0avgtext+0avgdata 41968maxresident)k
0inputs+0outputs (0major+2127minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.00system 0:00.02elapsed 96%CPU (0avgtext+0avgdata 42232maxresident)k
0inputs+0outputs (0major+2131minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.01system 0:00.03elapsed 90%CPU (0avgtext+0avgdata 42180maxresident)k
0inputs+0outputs (0major+2131minor)pagefaults 0swaps
$ env time uv run empty.py
apple
0.01user 0.01system 0:00.02elapsed 92%CPU (0avgtext+0avgdata 41876maxresident)k
0inputs+0outputs (0major+2131minor)pagefaults 0swaps
```

(0.02 * 6 + 0.03)/7 => Average: round down to 0.02 s

# OpenAI library + connection speed + inference speed
```
$ export OPENAI_API_KEY=$(msk_pass get openai_api_key_1411_main)
$ env time uv run existing.py
apple
0.65user 0.06system 0:01.11elapsed 64%CPU (0avgtext+0avgdata 62344maxresident)k
0inputs+0outputs (0major+14430minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.61user 0.06system 0:01.22elapsed 55%CPU (0avgtext+0avgdata 62420maxresident)k
0inputs+0outputs (0major+14427minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.62user 0.06system 0:01.14elapsed 59%CPU (0avgtext+0avgdata 62072maxresident)k
0inputs+0outputs (0major+14417minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.61user 0.06system 0:01.11elapsed 61%CPU (0avgtext+0avgdata 62096maxresident)k
0inputs+0outputs (0major+14427minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.60user 0.06system 0:01.03elapsed 64%CPU (0avgtext+0avgdata 62304maxresident)k
0inputs+0outputs (0major+14422minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.62user 0.05system 0:01.25elapsed 53%CPU (0avgtext+0avgdata 62236maxresident)k
0inputs+0outputs (0major+14417minor)pagefaults 0swaps
$ env time uv run existing.py
apple
0.63user 0.06system 0:01.21elapsed 57%CPU (0avgtext+0avgdata 62260maxresident)k
0inputs+0outputs (0major+14415minor)pagefaults 0swaps
```

(1.11 + 1.22 + 1.14 + 1.11 + 1.03 + 1.25 + 1.21) / 7 => Average: round down to
1.15 s

# C direct request (libcurl)
```
$ gcc minimal.c -lcurl -ljansson
$ export OPENAI_API_KEY=$(msk_pass get openai_api_key_1411_main)
$ env time ./a.out
apple
0.01user 0.00system 0:00.64elapsed 3%CPU (0avgtext+0avgdata 12280maxresident)k
0inputs+0outputs (0major+1002minor)pagefaults 0swaps
$ env time ./a.out
apple
0.01user 0.00system 0:00.35elapsed 7%CPU (0avgtext+0avgdata 12340maxresident)k
0inputs+0outputs (0major+1000minor)pagefaults 0swaps
$ env time ./a.out
apple
0.02user 0.01system 0:00.40elapsed 8%CPU (0avgtext+0avgdata 12296maxresident)k
0inputs+0outputs (0major+1001minor)pagefaults 0swaps
$ env time ./a.out
apple
0.02user 0.00system 0:00.38elapsed 7%CPU (0avgtext+0avgdata 12544maxresident)k
0inputs+0outputs (0major+1002minor)pagefaults 0swaps
$ env time ./a.out
apple
0.02user 0.00system 0:00.39elapsed 8%CPU (0avgtext+0avgdata 12408maxresident)k
0inputs+0outputs (0major+1000minor)pagefaults 0swaps
$ env time ./a.out
apple
0.02user 0.00system 0:00.39elapsed 6%CPU (0avgtext+0avgdata 12132maxresident)k
0inputs+0outputs (0major+995minor)pagefaults 0swaps
$ env time ./a.out
apple
0.02user 0.00system 0:00.42elapsed 8%CPU (0avgtext+0avgdata 12224maxresident)k
0inputs+0outputs (0major+999minor)pagefaults 0swaps
```

- (0.64 + 0.35 + 0.4 + 0.38 + 0.39 + 0.39 + 0.42)/7 => Average: Round down to 0.42
s
- ~0.73 s faster

# Python direct request (httpx)
```
$ export OPENAI_API_KEY=$(msk_pass get openai_api_key_1411_main)
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.62elapsed 33%CPU (0avgtext+0avgdata 38836maxresident)k
0inputs+0outputs (0major+7585minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.21user 0.01system 0:00.55elapsed 42%CPU (0avgtext+0avgdata 38832maxresident)k
0inputs+0outputs (0major+7580minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.19user 0.03system 0:00.87elapsed 25%CPU (0avgtext+0avgdata 38784maxresident)k
0inputs+0outputs (0major+7584minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.52elapsed 39%CPU (0avgtext+0avgdata 38712maxresident)k
0inputs+0outputs (0major+7576minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.01system 0:00.72elapsed 28%CPU (0avgtext+0avgdata 38716maxresident)k
0inputs+0outputs (0major+7573minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.19user 0.03system 0:00.61elapsed 36%CPU (0avgtext+0avgdata 38716maxresident)k
0inputs+0outputs (0major+7585minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.82elapsed 25%CPU (0avgtext+0avgdata 38840maxresident)k
0inputs+0outputs (0major+7575minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.52elapsed 39%CPU (0avgtext+0avgdata 38840maxresident)k
0inputs+0outputs (0major+7588minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.52elapsed 39%CPU (0avgtext+0avgdata 38700maxresident)k
0inputs+0outputs (0major+7569minor)pagefaults 0swaps
$ env time uv run minimal.py
apple
0.18user 0.02system 0:00.60elapsed 35%CPU (0avgtext+0avgdata 38832maxresident)k
0inputs+0outputs (0major+7584minor)pagefaults 0swaps
```

- (0.62 + 0.55 + 0.87 + 0.52 + 0.72 + 0.61 + 0.82 + 0.52 + 0.52 + 0.6)/10 =>
Average: round up to 0.64 s
- ~0.51 s faster than openai
- ~0.22 s slower than C libcurl
