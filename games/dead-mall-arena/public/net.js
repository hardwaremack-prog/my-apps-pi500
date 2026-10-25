// Dead Mall Arena LAN — tiny WebSocket client for the bundled server.
// The server relays every message to the other players and picks one "host"
// (the longest-connected player) whose browser runs the shared aliens and pickups.
(function(){
  'use strict';
  const handlers = {};
  const net = {
    online: false,        // true while connected to the LAN server
    available: location.protocol === 'http:' || location.protocol === 'https:',
    myId: null,
    hostId: null,
    isHost: true,         // offline / single player: you run everything yourself
    players: {},          // id -> {id, name}
    serverInfo: null,
    on(type, fn){ (handlers[type] = handlers[type] || []).push(fn); },
    send(t, d, to){
      if(!ws || ws.readyState !== 1) return false;
      try{ ws.send(JSON.stringify(to ? {t, d, to} : {t, d})); return true; }catch(e){ return false; }
    },
    connect(id, name){
      net.myId = id; myName = name; wantConnected = true;
      open();
    },
    rename(name){ myName = name; net.send('hello', {id: net.myId, name}); }
  };
  let ws = null, myName = 'Operator', wantConnected = false, retry = 0;
  function emit(type, msg){ (handlers[type] || []).forEach(fn => { try{ fn(msg.d, msg); }catch(e){ console.error('[net]', type, e); } }); }
  function setHost(id){
    net.hostId = id;
    const was = net.isHost;
    net.isHost = !net.online || id === net.myId;
    if(was !== net.isHost) emit('hostchange', {d:{isHost: net.isHost}});
  }
  function open(){
    if(!net.available) return;
    const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    try{ ws = new WebSocket(url); }catch(e){ scheduleRetry(); return; }
    ws.onopen = () => {
      retry = 0;
      ws.send(JSON.stringify({t:'hello', d:{id: net.myId, name: myName}}));
      if(document.hidden) ws.send(JSON.stringify({t:'away', d:{away:true}}));
    };
    ws.onmessage = (ev) => {
      let msg; try{ msg = JSON.parse(ev.data); }catch(e){ return; }
      if(msg.t === 'welcome'){
        net.online = true;
        net.players = {};
        (msg.d.players || []).forEach(p => net.players[p.id] = p);
        net.serverInfo = msg.d.server || null;
        setHost(msg.d.host);
        emit('status', {d:{online:true}});
      } else if(msg.t === 'join'){ net.players[msg.d.id] = msg.d; }
      else if(msg.t === 'leave'){ delete net.players[msg.d.id]; }
      else if(msg.t === 'host'){ setHost(msg.d.id); }
      emit(msg.t, msg);
    };
    ws.onclose = () => {
      const wasOnline = net.online;
      net.online = false; net.players = {};
      setHost(net.myId);
      if(wasOnline) emit('status', {d:{online:false}});
      scheduleRetry();
    };
    ws.onerror = () => { try{ ws.close(); }catch(e){} };
  }
  function scheduleRetry(){
    if(!wantConnected) return;
    retry = Math.min(retry + 1, 6);
    setTimeout(open, 500 * retry);
  }
  // a hidden tab stops animating, so it can't run the aliens: let the server hand hosting to someone awake
  document.addEventListener('visibilitychange', () => net.send('away', {away: document.hidden}));
  window.DMANet = net;
})();
