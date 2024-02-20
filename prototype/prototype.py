from collections import deque
from random import randint
from dataclasses import dataclass

@dataclass
class DBContent:
    name: str
    content: str

class DB:
    def __init__(self, name: str, queue: deque[DBContent]):
        self.name = name
        self.filename = f"{self.name}.txt"
        self._alive = True
        self.queue = queue

        with open(self.filename, 'w+') as f:
            f.write('')
        
    def write(self, text: str):
        with open(self.filename, "a+") as f:
            f.write(text)
            f.seek(0)
            db_content = f.read()

        self.queue.append(DBContent(self.name, db_content))

    @property
    def alive(self):
        return self._alive

    @alive.setter
    def alive(self, alivee: bool):
        self._alive = alivee
        print(f"DB {self.name} alive: {self._alive}")

        if self._alive is True:
            with open(self.filename, "r+") as f:
                db_content = f.read()
                if db_content != self.queue[0].content:
                    print(f"DB {self.name} triggering fault recovery, previous content: {db_content}")
                    f.seek(0)
                    f.write(self.queue[0].content)

if __name__ == "__main__":
    queue = deque([])
    dbs = [DB(f"{i}", queue) for i in range(1, 4)]

    while True:
        to_write = input("enter text to append:\n")
        responses = 0
        for db in dbs:
            if not db.alive:
                db.alive = True

            is_db_to_be_shutdown = randint(0, 10) <= 1
            if is_db_to_be_shutdown:
                db.alive = False

            if db.alive:
                db.write(to_write)
                responses += 1

        
        while len(queue) > responses:
            queue.popleft()
        print(queue)

    