#!/usr/bin/env python3

#
# Import built in packages
#
import logging
import platform
import os
import time
import socket
import subprocess
import signal
import psutil
import re

# Import 3th party modules:
#  - wexpect/pexpect to launch ant interact with subprocesses.
if platform.system() == 'Windows':
    import wexpect as expect
    print(expect.__version__)
else: # Linux
    import pexpect as expect


# The directory of this script file.
__here__ = os.path.dirname(os.path.realpath(__file__))

#
# Setup the logger
#

# The logger reads the `PYSCT_LOGGER_LEVEL` environment variable and set its the verbosity level
# based on that variable. The default is the WARNING level.
try:
    logger_level = os.environ['PYSCT_LOGGER_LEVEL']
    print(logger_level)
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


class PyXilException(Exception):
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
            raise PyXilException(ans[6:])
        raise PyXilException('Illegal start-string in protocol. Answer is: ' + ans)


default_vivado_prompt = 'Vivado% '

class Vivado():
    '''Vivado is a native interface towards the Vivado TCL console. You can run TCL commands in it
    using do() method. This is a quasi state-less class
    '''

    def __init__(self, executable, args=['-mode', 'tcl'], name='Vivado_01', prompt=default_vivado_prompt):
        self.childProc = None
        self.name = name
        self.prompt = prompt
        
        if executable is not None: # None is fake run
            self.childProc = expect.spawn(executable, args)
        
        
    def waitStartup(self, prompt=None):
        if prompt is None:
            prompt = self.prompt
        self.childProc.expect(prompt)
        # print the texts
        logger.debug(self.childProc.before + self.childProc.match.group(0))
        
        
    def do(self, cmd, prompt=None, wait_prompt=True, puts=False, errmsgs=[], encoding="utf-8", native_answer=False):
        ''' do a simple command in Vivado console
        '''
        if isinstance(cmd, str):
            cmd = cmd.encode()
        if self.childProc.terminated:
            logger.error('The process has been terminated. Sending command is not possible.')
            raise PyXilException('The process has been terminated. Sending command is not possible.')
        self.childProc.sendline(cmd)
        if prompt is None:
            prompt = self.prompt
        if wait_prompt:
            self.childProc.expect(prompt)
            logger.debug(str(cmd) + str(self.childProc.before) + str(self.childProc.match.group(0)))
            for em in errmsgs:
                if em.search(self.childProc.before):
                    logger.error('during running command: ' + repr(cmd) + repr(self.childProc.before))
                    raise PyXilException('during running command: ' + repr(cmd) + repr(self.childProc.before))
            if puts:
                print(cmd, end='')
                print(self.childProc.before, end='')
                print(self.childProc.match.group(0), end='')
                
            ans = self.childProc.before.decode(encoding)
            if native_answer:
                return ans
            else:
                # remove first line, which is always empty
                ans = os.linesep.join(ans.splitlines()[1:-1])
                return ans
                
        return None
        
    def get_var(self, varname):
        no_var_msg = 'can\'t read "{}": no such variable'.format(varname)
        # print(no_var_msg)
        errmsgs = [re.compile(no_var_msg.encode())]
        command = 'puts ${}'.format(varname)
        ans = self.do(command, errmsgs=errmsgs)
        
        return ans

    def set_var(self, varname, value):
        command = 'set {} {}'.format(varname, value)
        
        ans = self.do(command)
        
        return ans
    
    def get_property(self, propName, objectName, prompt=None, puts=False):
        ''' does a get_property command in vivado terminal. 
        
        It fetches the given property and returns it.
        '''
        cmd = 'get_property {} {}'.format(propName, objectName)
        self.do(cmd, prompt=prompt, puts=puts)
        val = [x for x in self.childProc.before.splitlines() if x ]
        return val[0]
    
    
    def set_property(self, propName, value, objectName, prompt=None, puts=False):
        ''' Sets a property.
        '''
        cmd = 'set_property {} {} {}'.format(propName, value, objectName)
        self.do(cmd, prompt=prompt, puts=puts)
        
        
    def exit(self):
        if self.childProc is None:
            return None
        if self.childProc.terminated:
            logger.warning('This process has been terminated.')
            return None
        else:
            self.do('exit', wait_prompt=False)
            return self.childProc.wait()
        

if __name__ == '__main__':
    """A small example of usage.
    """
    test_xsct = False
    test_vivado = True
    
    
    if test_xsct:
        win_xsct_executable = r'C:\Xilinx\SDK\2017.4\bin\xsct.bat'
        xsct_server = XsctServer(win_xsct_executable, port=PORT, verbose=False)
        xsct = Xsct('localhost', PORT)
        
        print("xsct's pid: {}".format(xsct.do('pid')))
        print(xsct.do('set a 5'))
        print(xsct.do('set b 4'))
        print("5+4={}".format(xsct.do('expr $a + $b')))

        xsct.close()
        xsct_server.stop_server()
    if test_vivado:
        # Path of Vivado executable:
        if platform.system() == 'Windows':
            vivadoPath = 'C:/Xilinx/Vivado/2017.4/bin/vivado.bat'
        else: # Linux
            vivadoPath = 'vivado'
            vivadoPath = '/home/beton/Xilinx/Vivado/2017.4/bin/vivado'
            vivadoPath = 'tclsh'
    
        vivado = Vivado(vivadoPath, prompt='%')
        vivado.waitStartup()
        print(vivado.do(b'pid'))
        print(vivado.set_var('a', '5'))
        print(vivado.set_var('b', '[expr $a + 4]'))
        print("5+4={}".format(vivado.get_var('b')))
        print("5+4={}".format(vivado.get_var('c')))
        vivado.exit()
        
        