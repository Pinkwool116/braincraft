/**
 * IPC Client for JavaScript-Python Communication
 * 
 * Handles communication with Python brain system via ZeroMQ.
 */

// TODO: Install zeromq package: npm install zeromq
// const zmq = require('zeromq');

class IPCClient {
    constructor(port = 9000) {
        this.port = port;
        this.pubPort = port + 1;
        this.connected = false;

        // TODO: Initialize ZeroMQ sockets
        // this.reqSocket = zmq.socket('req');
        // this.subSocket = zmq.socket('sub');

        this.commandHandlers = {};

        console.log(`IPC Client initialized for ports ${port}-${this.pubPort}`);
    }

    async connect() {
        /**
         * Connect to Python IPC server
         */
        try {
            // TODO: Connect sockets
            // this.reqSocket.connect(`tcp://localhost:${this.port}`);
            // this.subSocket.connect(`tcp://localhost:${this.pubPort}`);
            // this.subSocket.subscribe('');

            this.connected = true;
            console.log('IPC Client connected to Python server');

            // Start listening for commands from Python
            this._startCommandListener();

        } catch (error) {
            console.error('Failed to connect IPC client:', error);
            throw error;
        }
    }

    _startCommandListener() {
        /**
         * Listen for commands from Python brain system
         */
        // TODO: Implement command listener
        // this.subSocket.on('message', (msg) => {
        //     try {
        //         const data = JSON.parse(msg.toString());
        //         this._handleCommand(data);
        //     } catch (error) {
        //         console.error('Error handling command:', error);
        //     }
        // });

        console.log('Command listener started');
    }

    async _handleCommand(command) {
        /**
         * Handle command from Python
         * 
         * @param {Object} command - Command object from Python
         */
        const type = command.type;

        if (this.commandHandlers[type]) {
            try {
                await this.commandHandlers[type](command.data);
            } catch (error) {
                console.error(`Error executing command ${type}:`, error);
            }
        } else {
            console.warn(`No handler for command type: ${type}`);
        }
    }

    registerCommandHandler(type, handler) {
        /**
         * Register a command handler
         * 
         * @param {string} type - Command type
         * @param {Function} handler - Async handler function
         */
        this.commandHandlers[type] = handler;
        console.log(`Registered command handler: ${type}`);
    }

    async sendEvent(event) {
        /**
         * Send event to Python brain system
         * 
         * @param {Object} event - Event object
         * @returns {Object} Response from Python
         */
        if (!this.connected) {
            console.warn('IPC not connected, event not sent');
            return { status: 'error', error: 'Not connected' };
        }

        try {
            // TODO: Send event via REQ socket
            // await this.reqSocket.send(JSON.stringify(event));
            // const response = await this.reqSocket.receive();
            // return JSON.parse(response.toString());

            // Placeholder
            return { status: 'ok' };

        } catch (error) {
            console.error('Error sending event:', error);
            return { status: 'error', error: error.message };
        }
    }

    async sendStateUpdate(state) {
        /**
         * Send game state update to Python
         * 
         * @param {Object} state - Current game state
         */
        return await this.sendEvent({
            type: 'state_update',
            data: state
        });
    }

    async sendExecutionResult(result) {
        /**
         * Send code execution result to Python
         * 
         * @param {Object} result - Execution result
         */
        return await this.sendEvent({
            type: 'execution_result',
            data: result
        });
    }

    disconnect() {
        /**
         * Disconnect from Python server
         */
        // TODO: Close sockets
        // this.reqSocket.close();
        // this.subSocket.close();

        this.connected = false;
        console.log('IPC Client disconnected');
    }
}

module.exports = { IPCClient };
