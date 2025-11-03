"""
IPC Server

Handles communication between Python brain system and JavaScript game interface.
Uses ZeroMQ for efficient message passing.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Callable, Optional
import zmq
import zmq.asyncio

logger = logging.getLogger(__name__)

class IPCServer:
    """
    IPC Server for Python-JavaScript communication
    
    Uses two sockets:
    - REP socket for request-reply pattern (JS -> Python)
    - PUB socket for publish-subscribe pattern (Python -> JS)
    """
    
    def __init__(self, port: int = 9000):
        """
        Initialize IPC server
        
        Args:
            port: Base port number (will use port and port+1)
        """
        self.port = port
        self.pub_port = port + 1
        
        # Initialize ZeroMQ sockets
        self.context = zmq.asyncio.Context()
        self.rep_socket = self.context.socket(zmq.REP)
        self.pub_socket = self.context.socket(zmq.PUB)
        
        self.message_handlers = {}
        self.running = False
        
        logger.info(f"IPC server initialized on ports {port}-{self.pub_port}")
    
    async def start(self):
        """
        Start the IPC server
        
        Binds sockets and starts listening for messages.
        """
        # Bind sockets
        self.rep_socket.bind(f"tcp://*:{self.port}")
        self.pub_socket.bind(f"tcp://*:{self.pub_port}")
        
        self.running = True
        logger.info(f"IPC server started on ports {self.port} (REP) and {self.pub_port} (PUB)")
        
        # Start message receiving loop
        asyncio.create_task(self._receive_loop())
    
    async def _receive_loop(self):
        """
        Main loop for receiving messages from JavaScript
        
        Runs continuously and processes incoming messages.
        """
        logger.info("IPC receive loop started")
        
        while self.running:
            try:
                # Receive message from JS with timeout
                if await self.rep_socket.poll(timeout=100):  # 100ms timeout
                    message_bytes = await self.rep_socket.recv()
                    message = json.loads(message_bytes.decode('utf-8'))
                    
                    logger.debug(f"Received message: {message.get('type')}")
                    
                    # Process message
                    response = await self._handle_message(message)
                    
                    # Send response
                    response_bytes = json.dumps(response).encode('utf-8')
                    await self.rep_socket.send(response_bytes)
                else:
                    # No message, yield control
                    await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in receive loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming message from JavaScript
        
        Args:
            message: Message dictionary from JS
            
        Returns:
            Response dictionary
        """
        msg_type = message.get('type')
        data = message.get('data', {})
        
        logger.debug(f"Received message: {msg_type}")
        
        # Route message to appropriate handler
        if msg_type in self.message_handlers:
            try:
                result = await self.message_handlers[msg_type](data)
                return {'status': 'ok', 'result': result}
            except Exception as e:
                logger.error(f"Handler error for {msg_type}: {e}")
                return {'status': 'error', 'error': str(e)}
        else:
            logger.warning(f"No handler for message type: {msg_type}")
            return {'status': 'error', 'error': f'Unknown message type: {msg_type}'}
    
    def register_handler(self, msg_type: str, handler: Callable):
        """
        Register a message handler
        
        Args:
            msg_type: Message type to handle
            handler: Async function to handle the message
        """
        self.message_handlers[msg_type] = handler
        logger.debug(f"Registered handler for: {msg_type}")
    
    async def send_command(self, command: Dict[str, Any]):
        """
        Send command to JavaScript
        
        Uses PUB socket for one-way communication.
        
        Args:
            command: Command dictionary to send
        """
        try:
            # Send via PUB socket
            command_bytes = json.dumps(command).encode('utf-8')
            await self.pub_socket.send(command_bytes)
            logger.debug(f"Sent command: {command.get('type')}")
        except Exception as e:
            logger.error(f"Error sending command: {e}")
    
    async def stop(self):
        """Stop the IPC server"""
        self.running = False
        
        # Close sockets
        self.rep_socket.close()
        self.pub_socket.close()
        self.context.term()
        
        logger.info("IPC server stopped")
