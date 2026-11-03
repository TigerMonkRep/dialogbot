import json,sys
SPOKEN={"da":"dialogbot punktum app","en":"dialogbot dot app","de":"Dialogbot Punkt App","es":"dialogbot punto app","fr":"dialogbot point app","it":"dialogbot punto app","no":"dialogbot punktum app","sv":"dialogbot punkt app"}
l=sys.argv[1]; v=json.load(open(f"script/{l}.json"))["voice"]
scenes=[' <break time="0.7s" /> '.join(x.replace("dialogbot.app",SPOKEN[l]) for x in sc) for sc in v]
print(' <break time="1.6s" /> '.join(scenes))
