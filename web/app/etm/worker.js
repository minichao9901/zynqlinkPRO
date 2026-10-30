import {decodeTrace} from './decode.js';
self.onmessage=async event=>{
  try{const value=await decodeTrace(event.data);self.postMessage({ok:true,value});}
  catch(error){self.postMessage({ok:false,error:error.message});}
};
