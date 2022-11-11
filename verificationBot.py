import time
import json 
import discord
import random
import typing
import requests
import functools
import asyncio

from discord.ext import commands
from discord import app_commands

TOKEN = None # your discord bot token comes here
id = None # your server ID comes here

# simplest way to store wallets is to create a JSON
walletFile = "verificationBot\\wallets.json"

# name of the discord role you want to add to those holding your NFTs
roleName = "holder"

# you need to collect the NFT IDs one by one
# this is a MUST because there are no PolicyIDs on Ergo (yet)
assets = [
    #your NFT IDs comes here
    ]

def write(d, f):
    '''writes d dictionary into f json'''
    json_object = json.dumps(d, indent=4)
    with open(f, "w") as outfile:
        outfile.write(json_object)

def read(f):
    '''loads data from f json and returns it as d dictionary'''
    with open(f) as json_file:
        d = json.load(json_file)
    return d

def startBot():
    '''
    This is the standard way to start your discord bot.
    Careful: this code gives all the intents to your bot!
    '''
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
    class myBot(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.all())
            self.synced = False

        async def on_ready(self):
            await tree.sync(guild=discord.Object(id=id))
            self.synced = True
            print('The bot is online!')

            # checks the NFTs in wallets
            # and add/remove roles
            myCog = MyCog(bot)
            await myCog.sync_wallets()

    bot = myBot()
    tree = app_commands.CommandTree(bot)

    @tree.command(name='add_wallet', description='Register a wallet.', guild=discord.Object(id=id))
    async def self(interation: discord.Integration, address:str):
        '''creates a command with the name add_wallet. It needs a valid address as input'''
        walletDict = read(walletFile)

        # checks if address is valid
        if len(address) != 51 or address[0] != '9':
            await interation.response.send_message(f'This is not a valid address!')
            return
        
        # gets the current block height with an API call
        height = getErgoHeight()

        # creates n random number between 0.0001 and 0.0999
        n = random.uniform(0.0001, 0.0999)

        # creates a str that is exactly 6 character long
        n = str(n)[:6]

        # you have to send n number $erg FROM the wallet TO the wallet you want to register
        await interation.response.send_message(f'Alright, please send {n} $erg to yourself.')

        # runs a blocking function (in this case ownsWallet) in a non-blocking way
        success = await run_blocking(run_blocking, address, height, float(n)) 
        
        # success will be True if there is a spent box created after height in the wallet,
        # sent from that wallet, and box contains n number of $erg
        if success:
            await interation.followup.send(f"{interation.user.mention} is registered.")
            d = {}
            d[address] = []
            walletDict[str(interation.user)] = d
            write(walletDict, walletFile)
        else:
            interation.followup.send(f"{interation.user.mention} did **NOT** register!")

    # runs ownsWallet function in a non-blocking way until it is done
    async def run_blocking(blocking_func: typing.Callable, *args, **kwargs):
        func = functools.partial(ownsWallet, *args, **kwargs)
        return await bot.loop.run_in_executor(None, func)

    def ownsWallet(address, height, n):
        '''checks if you really own the wallet'''

        # starts a timer, checks every minute for "minutes" minute
        startTime = time.time()
        minutes = 60
        iterations = 0
        TxValid = False
        while iterations <= minutes and not TxValid:

            # gets all the boxes by address
            responseAPI = requests.get('https://api.ergoplatform.com/api/v1/boxes/byAddress/' + address)
            boxes = responseAPI.text
            boxesJson = json.loads(boxes)
            for box in boxesJson['items']:

                # checks if there is a box in the wallet created after user used the command
                if int(box['creationHeight']) >= height:

                    # checks if it contains the n number of $erg
                    if (float(box['value']) / 10**9) == n:

                        # get transaction details
                        responseAPI = requests.get('https://api.ergoplatform.com/api/v1/transactions/' + box['transactionId'])
                        txes = responseAPI.text
                        boxesJson = json.loads(txes)

                        # loops on the inputs, checks all the input addresses. If one is
                        # the address of the user -> user sent the tx
                        for box in boxesJson['inputs']:
                            if box['address'] == address:

                                # if all 3 requirement is true, than the tx is valid
                                TxValid = True

            iterations = iterations + 1
            time.sleep(60)

        return TxValid

    bot.run(TOKEN)

def getErgoHeight():
    '''returns current block height'''
    response_API = requests.get('https://api.ergoplatform.com/api/v1/info')
    data = response_API.text
    parseJson = json.loads(data)
    return parseJson['height']
    
def getNFTs(address):
    '''gets all the NFT IDs from an address'''
    response_API = requests.get('https://api.ergoplatform.com/api/v1/boxes/unspent/byAddress/' + address)
    data = response_API.text
    parseJson = json.loads(data)
    tokens = set()
    myNFTs = []
    # loop on boxes and collect tokens
    for box in parseJson['items']:
        for token in box['assets']:
            tokens.add(str(token['tokenId']))
    # check IDs for collected tokens
    for asset in assets:
        if asset in tokens:
            myNFTs.append(asset)

    return myNFTs

class MyCog(commands.Cog):
    '''
    With this class we can loop an async function every x minute in a non-blocking way.
    It is based on this tutorial:
    https://discordpy.readthedocs.io/en/stable/ext/tasks/index.html
    '''
    def __init__(self, bot):
        self.bot = bot

    async def sync_wallets(self):

        while True:
            print('Syncing the wallets.')
            walletDict = read(walletFile)

            # loops on the wallets 
            for wallet in walletDict:

                # delete everything from the list
                walletDict[wallet][list(walletDict[wallet].keys())[0]] = []

                # get the NFTs owned by the wallet
                myNFTs = getNFTs(list(walletDict[wallet].keys())[0])

                # add owned NFTs to the list
                for nft in myNFTs:
                    walletDict[wallet][list(walletDict[wallet].keys())[0]].append(nft)
                write(walletDict, walletFile)

            # loops on Discord members
            walletDict = read(walletFile)
            for guild in self.bot.guilds:
                for member in guild.members:
                    if str(member) in walletDict:
                        try:
                            for wallet in walletDict[str(member)]:
                                if wallet[0] != "N":
                                    # adds role with name roleName to members who holds more than 0 NFTs
                                    role = discord.utils.get(guild.roles, name=roleName)
                                    if len(walletDict[str(member)][wallet]) > 0 and role not in member.roles:
                                        await member.add_roles(role)
                                        print(f'Added role: {role} to {member}')
                                    # removes role with name roleName from member who holds less than 1 NFTs
                                    role = discord.utils.get(guild.roles, name=roleName)
                                    if len(walletDict[str(member)][wallet]) < 1 and role in member.roles:
                                        await member.remove_roles(role)
                                        print(f'Removed role: {role} to {member}')
                        except AttributeError:
                            print(f'There is no role named {roleName} on your discord server!')

            # sleeps for x minute
            await asyncio.sleep(300)

# starts the bot :)
if __name__ == "__main__":
    startBot()