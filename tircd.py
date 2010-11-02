#!/usr/bin/env python
# Simple IRC Server
# by y.fujii <y-fujii at mimosa-pudica.net>, public domain
#
# notes:
#     + Support messages for channels only.
#     + Nicknames don't need to be unique globally, but for each channels.

import re
import StringIO
import sys
import socket
import asyncore
import asynchat


class ReParser( object ):

	def __init__( self, src ):
		self.src = src


	def match( self, expr ):
		r = re.match( expr, self.src )
		if r is None:
			return None
		else:
			self.src = self.src[r.end():]
			return r.group( 1 )


def check( cond ):
	if cond:
		raise ValueError()


def checkStr( ex, s ):
	if re.match( ex, s ) is None:
		raise ValueError()


class Irc( object ):

	@staticmethod
	def parseMsg( buf ):
		parser = ReParser( buf )

		prefix = parser.match( ":([^ ]+) " )
		cmd = parser.match( "([^ ]+)" )
		if cmd is None:
			raise ValueError()

		args = []
		while True:
			arg = parser.match( " ([^:][^ ]+)" )
			if arg is None:
				break
			args.append( arg )
			
		arg = parser.match( " :(.*)" )
		if arg is not None:
			args.append( arg )

		return (prefix, cmd, args)


	@staticmethod
	def buildMsg( prefix, cmd, args ):
		buf = StringIO.StringIO()

		if prefix is not None:
			checkStr( "^[^\r\n ]*$", prefix )
			buf.write( ":" + prefix + " " )

		checkStr( "^[^\r\n ]+$", cmd )
		buf.write( cmd )

		if len( args ) > 0:
			for arg in args[:-1]:
				checkStr( "^[^:\r\n ][^\r\n ]*$", arg )
				buf.write( " " + arg )
			checkStr( "^[^\r\n]*$", args[-1] )
			buf.write( " :" + args[-1] )

		buf.write( "\r\n" )

		return buf.getvalue()


class Acceptor( asyncore.dispatcher ):

	def __init__( self, addr ):
		asyncore.dispatcher.__init__( self )

		#self.channels = collections.defaultdict( set )
		self.channels = {}

		self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
		self.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, 1 )
		self.bind( addr )
		self.listen( 5 )


	def handle_accept( self ):
		try:
			(sock, addr) = self.accept()
			ClientManager( sock, self.channels )
		except:
			pass
		

class ClientManager( asynchat.async_chat ):

	def __init__( self, sock, channels ):
		asynchat.async_chat.__init__( self, sock )
		self.set_terminator( "\r\n" )
		self.iBuf = StringIO.StringIO()
		self.channels = channels
		self.nick = None


	def collect_incoming_data( self, data ):
		self.iBuf.write( data )
	

	def found_terminator( self ):
		(prefix, cmd, args) = Irc.parseMsg( self.iBuf.getvalue() )
		self.iBuf = StringIO.StringIO()
		try:
			self.procMsg( prefix, cmd, args )
		except ValueError:
			pass
	
	
	def sendMsg( self, prefix, cmd, args ):
		self.push( Irc.buildMsg( prefix, cmd, args ) )


	def close( self ):
		# py3k compat
		#for (ch, clients) in list( self.channels.items() ):
		for (ch, clients) in self.channels.items():
			if self in clients:
				assert self.nick is not None
				for cl in clients:
					cl.sendMsg( self.nick, "PART", [ ch ] )
				clients.remove( self )
				if len( clients ) == 0:
					del self.channels[ch]

		asynchat.async_chat.close( self )


	def procMsg( self, prefix, cmd, args ):
		if cmd == "NICK":
			check( self.nick is None )
			check( len( args ) >= 1 )
			checkStr( "^[^: ][^ ]*$", args[0] )

			self.nick = args[0]
			self.sendMsg( "server", "001", [ self.nick, "Welcome." ] )
			self.sendMsg( "server", "376", [ self.nick, "" ] )

		elif cmd == "JOIN":
			check( self.nick is not None )
			check( len( args ) >= 1 )
			checkStr( "^[^: ][^ ]*$", args[0] )
			ch = args[0]

			if ch in self.channels:
				check( all( cl.nick != self.nick for cl in self.channels[ch] ) )
			else:
				self.channels[ch] = set()

			self.channels[ch].add( self )

			for cl in self.channels[ch]:
				cl.sendMsg( self.nick, "JOIN", [ ch ] )

			for cl in self.channels[ch]:
				self.sendMsg( "server", "353", [ self.nick, "=", ch, cl.nick ] )
			self.sendMsg( "server", "366", [ self.nick, ch, "" ] )

		elif cmd == "PART":
			check( self.nick is not None )
			check( len( args ) >= 1 )
			checkStr( "^[^: ][^ ]*$", args[0] )
			ch = args[0]
			check( ch in self.channels )
			check( self in self.channels[ch] )

			for cl in self.channels[ch]:
				cl.sendMsg( self.nick, "PART", [ ch ] )

			self.channels[ch].remove( self )
			if len( self.channels[ch] ) == 0:
				del self.channels[ch]

		elif cmd == "QUIT":
			self.close()

		elif cmd == "PRIVMSG":
			check( self.nick is not None )
			check( len( args ) == 2 )
			checkStr( "^[^: ][^ ]*$", args[0] )
			ch = args[0]
			check( ch in self.channels )
			check( self in self.channels[ch] )

			for cl in self.channels[ch]:
				if cl != self:
					cl.sendMsg( self.nick, "PRIVMSG", args )
		
		elif cmd == "PING":
			self.sendMsg( "server", "PONG", [ "server" ] + args )


def main():
	try:
		if len( sys.argv ) == 1:
			port = 6667
		elif len( sys.argv ) == 2:
			port = int( sys.argv[1] )
		else:
			raise ValueError()
	except ValueError:
		print "Usage: %s [port]" % sys.argv[0]
		sys.exit( 1 )

	Acceptor( ("", port) )
	asyncore.loop()


main()
