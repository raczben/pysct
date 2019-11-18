#!/usr/bin/env python3

#
# Import built in packages
#
import logging
import os
import time
import socket
import subprocess
import signal
import psutil

# The directory of this script file.
__here__ = os.path.dirname(os.path.realpath(__file__))

#
# Setup the logger
#

# The logger reads the `PYSCT_LOGGER_LEVEL` environment variable and set its the verbosity level
# based on that variable. The default is the WARNING level.
try:
    logger_level = os.environ['PYSCT_LOGGER_LEVEL']
except KeyError as _:
    logger_level = logging.WARNING

logger = logging.getLogger('pysct')
logger.setLevel(logger_level)
sh = logging.StreamHandler()
format = '%(asctime)s - %(filename)s::%(funcName)s - %(levelname)s - %(message)s'
formatter = logging.Formatter(format)
sh.setFormatter(formatter)
logger.addHandler(sh)

# xsct_line_end is the line endings in the XSCT console. It doesn't depend on the platform. It is
# always Windows-style \\r\\n.
xsct_line_end: str = '\r\n'

# The default host and port.
HOST = '127.0.0.1'  # Standard loop-back interface address (localhost)
PORT = 4567


class PysctException(Exception):
    """The exception for this project.
    """
    pass


class XsctServer:
    """The controller of the XSCT server application. This is an optional feature. The commands will
    be given to the client.
    """

    def __init__(self, xsct_executable=None, port=PORT, verbose=False):
        """ Initialize the Server object.
        
        :param xsct_executable: The full-path to the XSCT/XSDB executable
        :param port: TCP port where the server should be started
        :param verbose: True: prints the XSCT's stdout to python's stdout.
        """
        self._xsct_server = None
        if (xsct_executable is not None) or (port is not None):
            self.start_server(xsct_executable, port, verbose)

    def start_server(self, xsct_executable=None, port=PORT, verbose=False):
        """Starts the server.

        :param xsct_executable: The full-path to the XSCT/XSDB executable
        :param port: TCP port where the server should be started
        :param verbose: True: prints the XSCT's stdout to python's stdout.
        :return: None
        """
        if (xsct_executable is None) or (port is None):
            raise ValueError("xsct_executable and port must be non None.")
        start_server_command = 'xsdbserver start -port {}'.format(port)
        start_command = '{} -eval "{}" -interactive'.format(xsct_executable, start_server_command)
        logger.info('Starting xsct server: %s', start_command)
        if verbose:
            stdout = None
        else:
            stdout = open(os.devnull, 'w')
        self._xsct_server = subprocess.Popen(start_command, stdout=stdout)
        logger.info('xsct started with PID: %d', self._xsct_server.pid)

    def _start_dummy_server(self):
        """Starts a dummy server, just for test purposes.
        
        :return: None
        """
        dummy_executable = os.path.join(__here__, 'tests', 'dummy_xsct.tcl')
        start_command = 'tclsh {}'.format(dummy_executable)
        logger.info('Starting xsct server: %s', start_command)
        stdout = None
        self._xsct_server = subprocess.Popen(start_command, stdout=stdout)
        logger.info('xsct started with PID: %d', self._xsct_server.pid)

    def stop_server(self, wait=True):
        """Kills the server.

        :param wait: Wait for complete kill, or just send kill signals.
        :return: None
        """
        if not self._xsct_server:
            logger.debug('The server is not started or it has been killed.')
            return

        poll = self._xsct_server.poll()
        if poll is None:
            logger.debug("The server is alive, let's kill it.")

            # Kill all child process the XSCT starts in a terminal.
            current_process = psutil.Process(self._xsct_server.pid)
            children = current_process.children(recursive=True)
            for child in reversed(children):
                logger.debug("Killing child with pid: %d", child.pid)
                os.kill(child.pid, signal.SIGTERM)  # or signal.SIGKILL

            if wait:
                poll = self._xsct_server.poll()
                while poll is None:
                    logger.debug("The server is still alive, wait for it.")
                    time.sleep(.1)
                    poll = self._xsct_server.poll()

            self._xsct_server = None

        else:
            logger.debug("The server is not alive, return...")


class Xsct:
    """The XSCT client class. This communicates with the server and sends commands.
    """

    def __init__(self, host=HOST, port=PORT):
        """Initializes the client object.

        :param host: the URL of the machine address where the XSDB server is running.
        :param port: the port of the the XSDB server is running.
        """
        self._socket = None

        if host is not None:
            self.connect(host, port)

    def connect(self, host=HOST, port=PORT, timeout=10):
        """Connect to the xsdbserver

        :param host: Host machine where the xsdbserver is running.
        :param port: Port of the xsdbserver.
        :param timeout: Set a timeout on blocking socket operations. The value argument can be a non-negative float
        expressing seconds.
        :return: None
        """
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((host, port))
        if timeout is not None:
            self._socket.settimeout(timeout)
        logger.info('Connected to: %s...', repr((host, port)))

    def close(self):
        """Closes the connection

        :return: None
        """
        self._socket.close()

    def send(self, msg):
        """Sends a simple message to the xsdbserver through the socket. Note, that this method don't appends
        line-endings. It just sends natively the message. Use `do` instead.

        :param msg: The message to be sent.
        :return: Noting
        """
        if isinstance(msg, str):
            msg = msg.encode()
        logger.debug('Sending message: %s ...', repr(msg))
        self._socket.sendall(msg)

    def recv(self, bufsize=1024, timeout=None):
        """Receives the answer from the server. Not recommended to use it natively. Use `do`

        :param bufsize:The maximum amount of data to be received at once is specified by bufsize.
        :param timeout:
        :return:
        """
        if timeout is not None:
            self._socket.settimeout(timeout)
        ans = ''
        while True:
            data = self._socket.recv(bufsize)
            logger.debug('Data received: %s ...', repr(data))
            ans += data.decode("utf-8")
            ans = ans.split(xsct_line_end)
            if len(ans) > 1:
                return ans[0]

    def do(self, command):
        """The main function of the client. Sends a command and returns the return value of the command.

        :param command:
        :return:
        """
        command += xsct_line_end
        logger.info('Sending command: %s ...', repr(command))
        self.send(command)
        ans = self.recv()
        if ans.startswith('okay'):
            return ans[5:]
        if ans.startswith('error'):
            raise PysctException(ans[6:])
        raise PysctException('Illegal start-string in protocol. Answer is: ' + ans)


if __name__ == '__main__':
    """A small example of usage.
    """
    win_xsct_executable = r'C:\Xilinx\SDK\2017.4\bin\xsct.bat'
    xsct_server = XsctServer(win_xsct_executable, port=PORT, verbose=False)
    xsct = Xsct('localhost', PORT)
    
    print("xsct's pid: {}".format(xsct.do('pid')))
    print(xsct.do('set a 5'))
    print(xsct.do('set b 4'))
    print("5+4={}".format(xsct.do('expr $a + $b')))

    xsct.close()
    xsct_server.stop_server()
