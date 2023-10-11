# ipc_utils
  
A set of utilities for inter-process communication.  
Only compatible with Linux.  
  
## usage
  
IPCClient recieves data from an IPCServer, IPCServer sends data to an IPCClient.  
  
First, set up logging (provided through the `logging` module) if you want.  
Something like `logging.basicConfig(level=logging.WARN)` is a good default.  
  
Next, instantiate the class you want to use:  
```py
import ipc_server

server = ipc_server.IPCServer()
```
  
Then call `initialize()` on that instance.  
Pass it a unique string (preferably your app's name).    
Use the same string between your IPCServer and IPCClient.             
If you're using IPCClient, pass it a callback function as well.  
This callback will be invoked when the IPCClient recieves data, and it must take 1 positional argument.  
  
```py
def example_callback(data):
    print(f"Received {data} from server")

client = ipc_client.IPCClient()
client.initialize('example', example_callback)
```
  
`initialize()` will block until the client and server connect.  
  
Once connected, you can call `IPCServer.write(<data>)` to send data to the IPCClient.  
Data you send must be valid JSON.  
When the IPCClient recieves data, it calls the callback you registered and passes it the data.
  
For example:
```py
server.write('{"data":"test"}')
```
results in (on the client side):
```
>>> Received {'data': 'test'} from server
```
  
Your application must notify your IPC server / client of an impending shutdown to ensure it exits cleanly.  
To do this, run `shutdown_ipc` on either the server or client.
This performs some cleanup, notifies the other end, and stops the IPC thread.
Calling this on a Client will shut down the Server on the other end. (and vice versa)
