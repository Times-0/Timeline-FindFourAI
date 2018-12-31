from Timeline.Utils.Plugins.IPlugin import IPlugin, IPluginAbstractMeta, Requirement
from Timeline.Utils.Plugins import extend

from Timeline.Server.Constants import TIMELINE_LOGGER, LOGIN_SERVER, WORLD_SERVER
from Timeline.Utils.Events import Event, PacketEventHandler, GeneralEvent
from Timeline.Handlers.Games.FindFour import FindFour
from Timeline.Database.DB import Penguin
# from Timeline.Server.Penguin import Penguin as Bot

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor

from collections import deque
from time import sleep, time
import logging


class FindFourAI(IPlugin):
    """
	Adds an intelligent find four bot to the four lounge!
	Make sure you have dassets.swf active!
	"""

    requirements = [Requirement(**{'name': 'Commands', 'developer': 'Dote'})]
    name = 'FindFourAI'
    developer = 'Dote'

    AI_username = 'AI$FindFour'  # username of bot in the database
    Bots = dict()  # engine => Bot

    AI = None
    Call_AI_Command = "Find4"

    def __init__(self):
        super(FindFourAI, self).__init__()

        self.logger = logging.getLogger(TIMELINE_LOGGER)
        self.Bots = {}

        self.AICreatedDefer = self.setupAI()
        self.setupCommands()
        self.logger.debug("FindFour AI Active!")
        self.logger.debug("Please ensure you have dassets.swf active!")

        GeneralEvent.on('onEngine', self.attachBotToServer)

    def Play4(self, client, params):
        if client['room'].ext_id is not 220:
            return

        engine = client.engine
        if engine not in self.Bots:
            return client.send('sm', client['id'], "Sorry, bot is not available in this server!")

        AI = self.Bots[engine]['bot']
        if self.Bots[engine]['playing'] is not None:
            return client.send('sm', AI['id'],
                               "Sorry, am currently playing with {}".format(self.Bots[engine]['playing']['nickname']))

        try:
            difficulty = int(params[0])
        except:
            difficulty = 2  # default

        if difficulty > self.Bots[engine]['difficulty'] or difficulty < 1:
            difficulty = self.Bots[engine]['difficulty']  # maximum

        client.send('sm', AI['id'], "Let's play! Difficulty level set to {}".format(difficulty))
        sleep(3)

        client.send('sm', AI['id'], "Finding a board to play...")
        AvailableBoard = self.getFourBoard(engine)

        if AvailableBoard is None:
            return client.send('sm', AI['id'], "Sorry, no boards are available to play! :(")

        self.Bots[engine]['playing'] = client
        AI.penguin.difficulty = difficulty

        GeneralEvent.on('Table-Left-{}-{}'.format(client['id'], AvailableBoard.table), self.ClientLeft)

        client.send('zaf', AvailableBoard.table)  # make sure you have dote's assets
        Event.call('JoinTable-{}'.format(AvailableBoard.table), AI, AvailableBoard.table)

        AI['room'].send('sm', AI['id'],
                        "FindFour: {} V/S {}, difficulty: {}, started!".format(AI['nickname'], client['nickname'],
                                                                               difficulty))
        AI['game'].joinGame(AI)

    def makeNextTurn(self, AI):
        FourGame = AI['game']
        if FourGame is None:
            return

        FourBoard = list(FourGame.FourGame)

        nextMove = self.Bots[AI.engine]['algorithm'].calculateNextMove(FourBoard, AI['difficulty'])
        x, y = nextMove[0]

        AI.penguin.lastMoved = True
        FourGame.play(AI, [y, x])

    def manipulateSend(self, AI, *a):
        if len(a) < 2:
            return

        FourGame = AI['game']

        if a[0] == 'sz':
            self.makeNextTurn(AI)
        elif a[0] == 'zm':
            if FourGame.currentPlayer() is not AI:
                reactor.callLater(1, self.makeNextTurn, AI)

    def ClientLeft(self, client, FourGame):
        GeneralEvent.removeListener('Table-Left-{}-{}'.format(client['id'], FourGame.table), self.ClientLeft)
        if client.engine not in self.Bots:
            return

        FourGame.remove(self.Bots[client.engine]['bot'])
        self.Bots[client.engine]['playing'] = None

        AI = self.Bots[client.engine]['bot']
        AI['room'].send('sm', AI['id'],
                        "I've completed my game with {}. Ready for next round!".format(client['nickname']))

    def getFourBoard(self, engine):
        FourLounge = self.Bots[engine]['Room']
        _id = FourLounge.ext_id

        RoomHandler = engine.roomHandler
        if not _id in RoomHandler.ROOM_CONFIG.FourGame:
            return None

        Tables = RoomHandler.ROOM_CONFIG.FourGame[_id]
        for table in Tables:
            table = RoomHandler.ROOM_CONFIG.FourGame[_id][table]
            if table.FourStarted == False and len(table.Waddling) == 0:
                return table

        return None

    @inlineCallbacks
    def attachBotToServer(self, engine, defer=None):
        if defer is not None:
            engine = defer

        if engine.type is not WORLD_SERVER:
            return

        if self.AI is None:
            self.AICreatedDefer.addCallback(self.attachBotToServer, engine)
            return

        AI = engine.protocol(engine)
        AI.dbpenguin = self.AI
        AI.penguin.id = self.AI.id
        # Nullify major methods
        AI.disconnect = AI.makeConnection = lambda *x, **y: None
        # might need this to identify next moves!
        AI.send = lambda *x: self.manipulateSend(AI, *x)
        AI.initialize()

        yield AI['RefreshHandler'].CacheInitializedDefer

        AI.penguin.x = 351
        AI.penguin.y = 269
        AI.penguin.frame = 24

        FourLounge = engine.roomHandler.getRoomByExtId(220)
        #                                                       increasing difficulty may increase time to process next move
        self.Bots[engine] = {'bot': AI, 'algorithm': FindFourAlgorithm(), 'difficulty': 3, 'Room': FourLounge,
                             'playing': None}  # Attach algo to each FindFour game object created suring gameplay
        FourLounge.append(AI)

        self.logger.debug('FindFour AI added to %s', engine)

    def setupCommands(self):
        CommandsPlugin = self.dependencies[0]

        if self.Call_AI_Command not in CommandsPlugin.__commands__:
            CommandsPlugin.__commands__.append(self.Call_AI_Command)

        GeneralEvent.on('command={}'.format(self.Call_AI_Command.lower()), self.Play4)
        self.logger.debug("FindFour AI Call Command set. Command : %s", self.Call_AI_Command)

    # Maybe make a comprehensive link between a bot plugin and this AI, to a specific room?
    @inlineCallbacks
    def setupAI(self):
        AIExists = yield Penguin.exists(['`Username` = ?', self.AI_username])

        if not AIExists:
            yield self.createAI()

        if self.AI is None:
            self.AI = yield Penguin.find(where=['Username = ?', self.AI_username], limit=1)

    @inlineCallbacks
    def createAI(self):
        self.AI = Penguin(username=self.AI_username, nickname="FindFour AI", password='', email='me@me.me')
        yield self.AI.save()
        yield self.AI.refresh()  # update values from DB


class FindFourAlgorithm(object):

    def checkWin(self, FourGame, player=0, x=0, y=0, dx=1, dy=1, dp=4):
        dw = 0
        player += 1

        while 0 <= x < len(FourGame) and 0 <= y < len(FourGame[x]):
            advantage = FourGame[x][y] == player
            dw = dw * advantage + advantage

            if dw > dp - 1:
                return True

            x += dx
            y += dy

        return False

    def won(self, FourGame, player=0, dp=4):

        # horizontal win
        for i in range(len(FourGame)):
            if self.checkWin(FourGame, player, i, 0, 0, 1, dp):
                return 1

        # vertical win
        for i in range(len(FourGame[0])):
            if self.checkWin(FourGame, player, 0, i, 1, 0, dp):
                return 2

        # diagonal win
        for i in range(len(FourGame)):
            for j in range(len(FourGame[i])):
                if self.checkWin(FourGame, player, i, j, 1, 1, dp) or self.checkWin(FourGame, player, i, j, -1, -1,
                                                                                    dp) or self.checkWin(FourGame,
                                                                                                         player, i, j,
                                                                                                         -1, 1,
                                                                                                         dp) or self.checkWin(
                        FourGame, player, i, j, 1, -1, dp):
                    return 3

        # Tie
        if 0 not in sum(FourGame, []):
            return -1

        return 0

    def isValidChip(self, FourGame, x, y):
        if not (0 <= x < len(FourGame) and 0 <= y < len(FourGame[0])):
            return False

        if 0 <= x < len(FourGame) - 1:
            if FourGame[x + 1][y] == 0:
                return False

        return FourGame[x][y] == 0

    def playableChips(self, FourGame):
        chips = list()

        for i in range(len(FourGame)):
            for j in range(len(FourGame[i])):
                if self.isValidChip(FourGame, i, j):
                    chips.append((i, j))

        return chips

    def score(self, FourGame):
        winnable = 0

        for move in self.playableChips(FourGame):
            FourGame[move[0]][move[1]] = 1
            if self.won(FourGame, 0):
                winnable += 1

            FourGame[move[0]][move[1]] = 2
            if self.won(FourGame, 1):
                winnable -= 1

            FourGame[move[0]][move[1]] = 0

        return winnable

    def calculateNextMove(self, FourGame, depth=2, turn=-1):
        if self.won(FourGame, 0):
            return ((-1, -1), 500)
        elif self.won(FourGame, 1):
            return ((-1, -1), -500)

        player = 1 if turn < 0 else 2
        _FourGame = list(FourGame)
        FourGame = FourGame

        if depth == 0:
            return ((-1, -1), turn * self.score(FourGame))

        emptySlots = self.playableChips(FourGame)
        bestMove = (emptySlots[0], 1000 * turn)  # move, score for current move

        for move in emptySlots:
            x, y = move
            FourGame[x][y] = player  # try the move
            _FourGame = FourGame

            result = self.calculateNextMove(FourGame, depth - 1, -turn)  # test the move for opponents advantage
            _FourGame[x][y] = 0  # undo the move
            FourGame = _FourGame

            if self.isValidChip(FourGame, x, y):
                if (turn < 0 and result[1] > bestMove[1] or turn > 0 and result[1] < bestMove[1]):
                    bestMove = ((x, y), result[1])
                elif abs(result[1]) == 500 and result[1] == bestMove[1]:
                    bestMove = ((x, y), result[1])

        return bestMove
