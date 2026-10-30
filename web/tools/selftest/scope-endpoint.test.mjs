import test from 'node:test';
import assert from 'node:assert/strict';
import {findScopeEndpoint} from '../../app/scope/transport.js';
const configuration=endpoints=>({interfaces:[{interfaceNumber:0,alternates:[{interfaceClass:0xff,endpoints:endpoints.map(endpointNumber=>({endpointNumber,type:'bulk',direction:'in'}))}]}]});
test('HSS finds legacy IN3 and Zynq IN7 while excluding the ETM IN2 endpoint',()=>{
  assert.equal(findScopeEndpoint(configuration([1,3])).ep.endpointNumber,3);
  assert.equal(findScopeEndpoint(configuration([1,7,2])).ep.endpointNumber,7);
  assert.equal(findScopeEndpoint(configuration([1,2])),null);
  const zynq=configuration([1,7,2]);
  zynq.interfaces.unshift({interfaceNumber:2,alternates:[{interfaceClass:0x0a,endpoints:[{endpointNumber:3,type:'bulk',direction:'in'}]}]});
  assert.equal(findScopeEndpoint(zynq).ep.endpointNumber,7);
});
