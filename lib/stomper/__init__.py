"""
This is a python client implementation of the STOMP protocol. It aims
to be transport layer neutral. This module provides functions to create
and parse STOMP messages in a programatic fashion.

The examples package contains two examples using twisted as the transport 
framework. Other frameworks can be used and I may add other examples as
time goes on.

The STOMP protocol specification maybe found here:

 * http://stomp.codehaus.org/Protocol

I've looked and the stomp client by Jason R. Briggs and have based the message
generation on how his client did it. The client can be found at the follow 
address however it isn't a dependancy.

 * http://www.briggs.net.nz/log/projects/stomppy

In testing this library I run against ActiveMQ project. The server runs
in java, however its fairly standalone and easy to set up. The projects
page is here:

 * http://activemq.apache.org/


(c) Oisin Mulvihill, 2007-07-26.
License: http://www.apache.org/licenses/LICENSE-2.0

"""
import re
import uuid


NO_REPONSE_NEEDED = ''


def unpack_frame(message):
    """Called to unpack a STOMP message into a dictionary.
    
    returned = {
        # STOMP Command:
        'cmd' : '...',
        
        # Headers e.g.
        'headers' : {
            'destination' : 'xyz',
            'message-id' : 'some event',
            :
            etc,
        }
        
        # Body:
        'body' : '...1234...',
    }
        
    """
    body = []
    returned = dict(cmd='', headers={}, body='')
    
    breakdown = message.split('\n')

    # Get the message command:
    returned['cmd'] = breakdown[0]
    breakdown = breakdown[1:]

    def headD(field):
        # find the first ':' everything to the left of this is a
        # header, everything to the right is data:
        index = field.find(':')
        if index:
            header = field[:index].strip()
            data = field[index+1:].strip()
#            print "header '%s' data '%s'" % (header, data)            
            returned['headers'][header.strip()] = data.strip()

    def bodyD(field):
        body.append(field)

    # Recover the header fields and body data
    handler = headD
    for field in breakdown:
#        print "field:", field
        if field.strip() == '':
            # End of headers, it body data next.
            handler = bodyD
            continue

        handler(field)

    # Stich the body data together:
    body = "".join(body)
    returned['body'] = body.replace('^@', '')
    
    return returned

        
def abort(transactionid):
    """STOMP abort transaction command.

    Rollback whatever actions in this transaction.
        
    transactionid:
        This is the id that all actions in this transaction.
    
    """
    return "ABORT\ntransaction: %s\n\n\x00\n" % transactionid


def ack(messageid, transactionid=None):
    """STOMP acknowledge command.
    
    Acknowledge receipt of a specific message from the server.

    messageid:
        This is the id of the message we are acknowledging,
        what else could it be? ;)
    
    transactionid:
        This is the id that all actions in this transaction 
        will have. If this is not given then a random UUID
        will be generated for this.
    
    """
    header = 'message-id: %s' % messageid

    if transactionid:
        header = 'message-id: %s\ntransaction: %s' % (messageid, transactionid)
        
    return "ACK\n%s\n\n\x00\n" % header

    
def begin(transactionid=None):
    """STOMP begin command.

    Start a transaction...
    
    transactionid:
        This is the id that all actions in this transaction 
        will have. If this is not given then a random UUID
        will be generated for this.
    
    """
    if not transactionid:
        # Generate a random UUID:
        transactionid = uuid.uuid4()

    return "BEGIN\ntransaction: %s\n\n\x00\n" % transactionid

    
def commit(transactionid):
    """STOMP commit command.

    Do whatever is required to make the series of actions
    permenant for this transactionid.
        
    transactionid:
        This is the id that all actions in this transaction.
    
    """
    return "COMMIT\ntransaction: %s\n\n\x00\n" % transactionid


def connect(username, password):
    """STOMP connect command.
    
    username, password:
        These are the needed auth details to connect to the 
        message server.
    
    After sending this we will receive a CONNECTED
    message which will contain our session id.
    
    """
    return "CONNECT\nlogin:%s\npasscode:%s\n\n\x00\n" % (username, password)


def disconnect():
    """STOMP disconnect command.
    
    Tell the server we finished and we'll be closing the
    socket soon.
    
    """
    return "DISCONNECT\n\n\x00\n"

    
def send(dest, msg, transactionid=None):
    """STOMP send command.
    
    dest:
        This is the channel we wish to subscribe to
    
    msg:
        This is the message body to be sent.
        
    transactionid:
        This is an optional field and is not needed
        by default.
    
    """
    transheader = ''
    
    if transactionid:
        transheader = 'transaction: %s' % transactionid
        
    return "SEND\ndestination: %s\n%s\n%s\x00\n" % (dest, transheader, msg)
    
    
def subscribe(dest, ack='auto'):
    """STOMP subscribe command.
    
    dest:
        This is the channel we wish to subscribe to
    
    ack: 'auto' | 'client'
        If the ack is set to client, then messages received will
        have to have an acknowledge as a reply. Otherwise the server
        will assume delivery failure.
    
    """
    return "SUBSCRIBE\ndestination: %s\nack: %s\n\n\x00\n" % (dest, ack)


def unsubscribe(dest):
    """STOMP unsubscribe command.
    
    dest:
        This is the channel we wish to subscribe to
    
    Tell the server we no longer wish to receive any
    further messages for the given subscription.
    
    """
    return "UNSUBSCRIBE\ndestination:%s\n\n\x00\n" % dest
    

class Engine(object):
    """This is a simple state machine to return a response to received 
    message if needed.
    
    """
    def __init__(self):
        self.sessionId = ''
        
        self.doAck = False
        
        # Format COMMAND : Action
        self.states = {
            'CONNECTED' : self.connected,
            'MESSAGE' : self.ack,
        }
                
    def react(self, msg):
        """Called to provide a response to a message if needed.
        
        msg:
            This is a dictionary as returned by unpack_frame(...)

        returned:
            A message to return or an empty string.
            
        """
        returned = ""
        
        if self.states.has_key(msg['cmd']):
            returned = self.states[msg['cmd']](msg)
            
        return returned
        
        
    def connected(self, msg):
        """No reponse is needed to a connected frame. 
        
        This method stores the session id as a the 
        member sessionId for later use.
        
        returned:
            NOREPONSE
            
        """
        self.sessionId = msg['headers']['session']
        #print "connected: session id '%s'." % self.sessionId
        
        return NO_REPONSE_NEEDED


    def ack(self, msg):
        """Return an acknowlege message for the given message and transaction (if present)
        """
        if not self.doAck:
            return NO_REPONSE_NEEDED
            
        message_id = msg['headers']['message-id']

        transaction_id = None
        if msg['headers'].has_key('transaction-id'):
            transaction_id = msg['headers']['transaction-id']
        
        #print "acknowledging message id <%s>." % message_id
        return ack(message_id, transaction_id)



        