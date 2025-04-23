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
