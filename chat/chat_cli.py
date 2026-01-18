from chat.responder import answer

print("System Knowledge Bot (type 'exit' to quit)")
while True:
    q = input("> ")
    if q == "exit": break
    print(answer(q))
