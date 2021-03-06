import pickle
import time
from hashlib import sha256
from ecdsa import SigningKey, VerifyingKey
import KeysGeneration


# Block Class with it's basic attributes
class Block:
    def __init__(self, index, transactions, timestamp, previousHash, blockHash, reward, nonce, difficulty):
        self.id = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previousHash = previousHash
        self.hash = blockHash
        self.reward = reward
        self.nonce = nonce
        self.difficulty = difficulty
        self.objectDesc = ObjectDesc("Blocks",
                                     "(:id, :transactions, :timestamp, :previousHash, :hash, :reward, :nonce, :difficulty)",
                                     {}, "id", ["transactions"])
        self.objectDesc.setDatabaseValues(self.__dict__)

    def computeHash(self):
        # self.__dict__ => all attributes defined for the object Block
        blockString = pickle.dumps(self.__dict__)

        # sha256() => Hash it with sha256
        # hexdigest() => Returns the encoded data in hexadecimal format
        return (sha256(blockString)).hexdigest()

    # Function that mines the block by calling the computeHash function until it the resulting hash satisfies the block's difficulty
    def mine(self, wallet):
        self.transactions.append(wallet.constructCoinbaseTx(50, wallet.address, None))
        blockHash = self.computeHash()
        while not blockHash.startswith('0' * self.difficulty):
            self.nonce += 1
            blockHash = self.computeHash()
        self.hash = blockHash
        self.objectDesc.setDatabaseValues(self.__dict__)
        return blockHash

    # Function that calculates the block's reward
    def finalReward(self):
        for tx in self.transactions:
            self.reward += tx.fees


# Input Class that is stored in the inputs attribute of the Transaction class
class Input:
    def __init__(self, value, address, prevTxId, lockingScript, scriptSig):
        self.value = value
        self.address = address
        self.prevTxId = prevTxId
        self.lockingScript = lockingScript
        self.scriptSig = scriptSig


# Output Class that is stored in the outputs attribute of the Transaction class
class Output:
    def __init__(self, index, value, address, transactionId, lockingScript):
        self.id = index
        self.value = value
        self.address = address
        self.transactionId = transactionId
        self.lockingScript = lockingScript
        self.objectDesc = ObjectDesc("UTXO", "(:id, :value, :address, :transactionId, :lockingScript)",
                                     {}, "lockingScript", [])
        self.objectDesc.setDatabaseValues(self.__dict__)


# Transaction Class that is stored in the transactions attribute of the Block class
class Transaction:
    def __init__(self, index=None, type=None, inputs=None, outputs=None, timestamp=time.time(), transactionId="",
                 fees=None):
        self.id = index
        self.type = type
        if inputs is None:
            inputs = []
        if outputs is None:
            outputs = []
        self.inputs = inputs
        self.outputs = outputs
        self.timestamp = timestamp
        self.transactionId = transactionId
        self.fees = fees
        self.objectDesc = ObjectDesc("Transactions",
                                     "(:id, :type, :inputs, :outputs, :timestamp, :transactionId, :fees)",
                                     {}, "transactionId", ["inputs", "outputs"])
        self.objectDesc.setDatabaseValues(self.__dict__)

    # Function that computes and sets the transaction's id
    def computeTxId(self):
        txId = ""
        for input in self.inputs:
            d = input.__dict__
            for attrib in d:
                txId += sha256(str(d[attrib]).encode()).hexdigest()
        txId += sha256(str(self.timestamp).encode()).hexdigest()
        self.transactionId = (sha256(txId.encode())).hexdigest()
        self.objectDesc.setDatabaseValues(self.__dict__)
        return self.transactionId

    # Function that adds an input to the tx
    def addInput(self, input):
        self.inputs.append(input)
        self.objectDesc.setDatabaseValues(self.__dict__)

    # Function that adds an output to the tx
    def addOutput(self, output):
        self.outputs.append(output)
        self.objectDesc.setDatabaseValues(self.__dict__)

    # Function that calculates the tx fees
    def calculateFees(self):
        self.fees = 0
        for input in self.inputs:
            self.fees += input.value * 0.01
        self.objectDesc.setDatabaseValues(self.__dict__)


# UnconfirmedTransaction class that inherits from the Transaction class
class UnconfirmedTransaction(Transaction):
    def __init__(self, index=None, type=None, inputs=None, outputs=None, timestamp=time.time(), transactionId="",
                 fees=None):
        super().__init__(index, type, inputs, outputs, timestamp, transactionId, fees)
        self.objectDesc.databaseTableName = 'Unconfirmed_Transactions'


# ObjectDesc Class that is stored as an attribute in every class
# This class enables the use of a single function to add/remove/update any object regardless of it's type
class ObjectDesc:
    def __init__(self, databaseTableName, databaseColumnNames, databaseValues, distinctAttrib, toPickleAttrib):
        self.databaseTableName = databaseTableName
        self.databaseColumnNames = databaseColumnNames
        self.databaseValues = databaseValues
        self.distinctAttrib = distinctAttrib
        self.toPickleAttrib = toPickleAttrib

    # Function that changes the instance's attributes
    def setDatabaseValues(self, dict):
        for attrib in dict:
            if attrib != "objectDesc":
                self.databaseValues[attrib] = dict[attrib]


# Wallet class that stores the node's wallet info as his address, public/private keys, etc...
class Wallet:
    def __init__(self, database):
        try:
            self.address = KeysGeneration.getAddress()
        except FileNotFoundError:
            KeysGeneration.generate()
            self.address = KeysGeneration.getAddress()
        self.database = database
        self.pubkey = VerifyingKey.from_pem(open("Keys\\PublicKey.pem").read())
        self.privkey = SigningKey.from_pem(open("Keys\\PrivateKey.pem").read())
        self.amount = self.balance()

    # Function that calculates the wallet's balance
    def balance(self):
        self.amount = 0
        # Getting the utxos that are owned by the wallet's address
        utxos = self.database.getUtxoList(self.address)
        # Adding all the utxos values
        if utxos:
            for i in range(0, len(utxos)):
                self.amount += float(utxos[i].value)
        return self.amount

    # Function that creates a normal tx (type 2)
    def constructTx(self, transactionSender, transactionReceiver, transactionAmount):
        # Checking of the sender has enough money or if the receiver address is valid
        if self.balance() < transactionAmount or len(transactionReceiver) != len(transactionSender):
            return None
        else:
            # Creating a UnconfirmedTransaction instance
            transaction = UnconfirmedTransaction(self.database.getLastObjectId("Unconfirmed_Transactions") + 1, 2)
            # Querying the UTXO table
            utxos = self.database.getUtxoList(self.address)
            transaction.addInput(self.outToIn(utxos[0]))
            s = 0

            # Converting UTXO'S to Inputs and adding them to the Transaction's Inputs List
            for utxo in transaction.inputs:
                s += utxo.value
                if s < transactionAmount:
                    transaction.addInput(self.outToIn(utxos[transaction.inputs.index(utxo) + 1]))

            txId = transaction.computeTxId()

            # Output to the receiver
            out1 = Output(self.database.getLastObjectId("UTXO") + 1, transactionAmount, transactionReceiver, txId, 0)
            transaction.addOutput(self.createOutScript(out1))

            # Output to the sender
            out2 = Output(self.database.getLastObjectId("UTXO") + 1, s - transactionAmount * 1.01, transactionSender,
                          txId, 0)
            transaction.addOutput(self.createOutScript(out2))

            transaction.calculateFees()
            transaction.objectDesc.setDatabaseValues(transaction.__dict__)
            return transaction

    # Function that creates a coinbase tx (transaction that rewards the miner and its type is 1)
    def constructCoinbaseTx(self, amount, address, outScript):
        # Creating the tx instance
        transaction = Transaction(self.database.getLastObjectId("Transactions") + 1, 1)
        # Computing its id
        transaction.computeTxId()
        # Creating the outputs then adding them to the transaction
        out = Output(self.database.getLastObjectId("UTXO") + 1, amount, address, transaction.transactionId, outScript)
        transaction.addOutput(self.createOutScript(out))

        transaction.calculateFees()
        transaction.objectDesc.setDatabaseValues(transaction.__dict__)
        return transaction

    # Function that returns the signature of the private key
    def sign(self, script):
        return self.privkey.sign(script)

    # Function that transforms an output instance to an input instance
    def outToIn(self, out):
        return Input(out.value, out.address, out.transactionId, out.lockingScript, self.sign(out.lockingScript))

    # Function that creates the locking script of the output
    def createOutScript(self, out):
        SEPERATOR = "<SEPERATOR>".encode()
        outScript = self.pubkey.to_string() + SEPERATOR + str(
            out.value).encode() + SEPERATOR + out.address.encode() + SEPERATOR + str(
            out.transactionId).encode() + SEPERATOR + str(time.time()).encode()
        out.lockingScript = outScript
        out.objectDesc.setDatabaseValues(out.__dict__)
        return out

    # Function that returns the pending coins of the wallet
    def getPendingAmount(self, sender):
        return self.database.getPendingAmount(sender)


# Database Class that queries,adds,deletes and updates any data desired
# on our defined classes (Blocks, UTXOS, Unconfirmed and Confirmed Transactions) in the database
class Database:
    def __init__(self, connection, cursor):
        self.conn = connection
        self.c = cursor

    # Function that gets the last object id from the database
    def getLastObjectId(self, tableName):
        if self.emptyTable(tableName):
            return 0
        else:
            self.c.execute("SELECT max(id) FROM {}".format(tableName))
            return self.c.fetchall()[0][0]

    # Function that gets the first object id from the database
    def getFirstObjectId(self, tableName):
        if self.emptyTable(tableName):
            return 0
        else:
            self.c.execute("SELECT min(id) FROM {}".format(tableName))
            return self.c.fetchall()[0][0]

    # Function that checks if the table in argument is empty
    def emptyTable(self, tableName):
        self.c.execute("SELECT * FROM {};".format(tableName))
        if self.c.fetchall():
            return False
        else:
            return True

    # Function that gets the object by id from the database
    def getObjectById(self, tableName, index):
        if tableName == "Blocks":
            block = Block(*self.getRawObjectById(tableName, index))
            self.unpickleObjectAttrib(block)
            return block
        if tableName == "Transactions":
            tx = Transaction(*self.getRawObjectById(tableName, index))
            self.unpickleObjectAttrib(tx)
            return tx
        if tableName == "Unconfirmed_Transactions":
            tx = UnconfirmedTransaction(*self.getRawObjectById(tableName, index))
            self.unpickleObjectAttrib(tx)
            return tx
        if tableName == "UTXO":
            output = Output(*self.getRawObjectById(tableName, index))
            self.unpickleObjectAttrib(output)
            return output

    # Function that gets the object by id from the database
    def getRawObjectById(self, tableName, index):
        self.c.execute("SELECT * FROM {} WHERE id=:id".format(tableName), {'id': index})
        res = self.c.fetchall()
        if res:
            return res[0]
        else:
            return None

    # Function that transforms raw data to an object
    @staticmethod
    def rawToObject(tableName, rawData):
        if tableName == "Blocks":
            block = Block(*rawData)
            return block
        if tableName == "Transactions":
            tx = Transaction(*rawData)
            return tx
        if tableName == "Unconfirmed_Transactions":
            tx = UnconfirmedTransaction(*rawData)
            return tx
        if tableName == "UTXO":
            output = Output(*rawData)
            return output

    # Function that sets an id to the object that won't create a conflict in the database
    def setObjectId(self, object):
        objectId = self.getLastObjectId(object.objectDesc.databaseTableName)
        object.id = objectId + 1
        object.objectDesc.databaseValues['id'] = object.id

    # Function that adds the designed object to the database
    def addObject(self, object, definitive=False):
        if not definitive:
            self.setObjectId(object)
        self.pickleObjectAttrib(object)
        with self.conn:
            self.c.execute(
                "INSERT INTO {} VALUES {}".format(object.objectDesc.databaseTableName,
                                                  object.objectDesc.databaseColumnNames),
                object.objectDesc.databaseValues)

    # Function that removes the designed object from the database
    def removeObject(self, object):
        distAttrib = object.objectDesc.distinctAttrib
        self.c.execute(
            "DELETE FROM {0} WHERE {1}=:{1}".format(object.objectDesc.databaseTableName, distAttrib),
            {'{}'.format(distAttrib): object.objectDesc.databaseValues[distAttrib]})
        self.conn.commit()

    # Function that returns the first object in the designed table
    def getFirstObject(self, tableName):
        minId = self.getFirstObjectId(tableName)
        return self.getObjectById(tableName, minId)

    # Function that returns a list of all UTXOS that have the designed address
    def getUtxoList(self, address):
        self.c.execute("SELECT * FROM UTXO WHERE address=:address", {'address': address})
        utxos = self.c.fetchall()
        utxoList = []
        if len(utxos) != 0:
            for i in range(0, len(utxos)):
                utxoList.append(Output(*utxos[i]))
        return utxoList

    # Function that returns the UTXO that have the designed locking script
    def getUtxoByScript(self, lockingScript):
        self.c.execute("SELECT * FROM UTXO WHERE lockingScript=:lockingScript", {'lockingScript': lockingScript})
        utxoId = self.c.fetchall()[0][0]
        return self.getObjectById("UTXO", utxoId)

    # Function that returns the tx that have the designed tx id
    def getTxByTxId(self, transactionId):
        try:
            self.c.execute("SELECT * FROM Transactions WHERE transactionId=:transactionId",
                           {'transactionId': transactionId})
            TxId = self.c.fetchall()[0][0]
            return self.getObjectById("Transactions", TxId)
        except IndexError:
            try:
                self.c.execute("SELECT * FROM Unconfirmed_Transactions WHERE transactionId=:transactionId",
                               {'transactionId': transactionId})
                TxId = self.c.fetchall()[0][0]
                return self.getObjectById("Unconfirmed_Transactions", TxId)
            except IndexError:
                return None

    # Function that returns a list of objects from the designed table
    def getObjectList(self, tableName):
        res = []
        self.c.execute("SELECT * FROM {}".format(tableName))
        for i in self.c.fetchall():
            res.append(self.getObjectById(tableName, i[0]))
        return res

    # Function that returns a list of ids from the designed table
    def getObjectIdList(self, tableName):
        self.c.execute("SELECT id FROM {}".format(tableName))
        return self.c.fetchall()

    # Function that pickles all the attributes in the toPickleAttrib of the designed object
    @staticmethod
    def pickleObjectAttrib(object):
        for attrib in object.objectDesc.toPickleAttrib:
            object.objectDesc.databaseValues[attrib] = pickle.dumps(object.objectDesc.databaseValues[attrib])

    # Function that unpickles all the attributes in the toPickleAttrib of the designed object
    @staticmethod
    def unpickleObjectAttrib(object):
        for attrib in object.objectDesc.toPickleAttrib:
            object.__dict__[attrib] = pickle.loads(object.objectDesc.databaseValues[attrib])

    # Function that returns how many coins are pending
    def getPendingAmount(self, sender):
        pending = 0
        moneyIn = 0
        unconfTxList = self.getObjectList("Unconfirmed_Transactions")
        for unconfTx in unconfTxList:
            inputs = unconfTx.inputs
            outputs = unconfTx.outputs
            for input in inputs:
                if input.address == sender:
                    pending += input.value
            for output in outputs:
                if output.address == sender:
                    moneyIn += output.value
        return pending, moneyIn

    # Function that searches for a Block or Tx with the designed parameter
    def search(self, param):
        try:
            p = int(param)
            try:
                return self.getObjectById("Blocks", p)
            except IndexError:
                return None
        except ValueError:
            return self.getTxByTxId(param)
