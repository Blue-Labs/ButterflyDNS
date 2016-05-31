'use strict';

// user editable part, if document.location.hostname is not correct
// alter this accordingly, it should be wss:// + hostname + /ws
var wsuri = 'wss://'+document.location.hostname+'/ws';

// that's all. please leave the rest of this to me. however, if you change
// something that you feel is beneficial to others, please tell us at
// https://github.com/Blue-Labs/ButterflyDNS/issues

// zone record types
var rtypes = ['A','AAAA','CNAME','HINFO','MBOXFW','MX','NAPTR','NS','PTR','SRV','TXT','URL',],
    ss,
    principal = '',
    ticket    = '';

// initial subscriptions; this will grow/shrink as people navigate
// recently_fired_events helps us debounce rapid succession events
var wamp_subscriptions = {},
    recently_fired_events = {};

function timeConverter(UNIX_timestamp){
  if (UNIX_timestamp === undefined) { return ''; }
  var a      = new Date(parseInt(UNIX_timestamp,10) * 1000);
  var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var year   = a.getFullYear();
  var month  = a.getMonth(); //months[a.getMonth()];
  var date   = a.getDate();
  var hour   = a.getHours();
  var min    = a.getMinutes() < 10 ? '0'+a.getMinutes() : a.getMinutes();
  var sec    = a.getSeconds() < 10 ? '0'+a.getSeconds() : a.getSeconds();
  var time   = year +'-'+ month +'-'+ date + ' ' + hour + ':' + min + ':' + sec ;
  return time;
}

function SetCaretAtEnd(elem) {
    elem = $(elem).get(0);
    var elemLen = elem.value.length;

    // if it's type=number, simply ignore it. W3WG decided we didn't
    // need cursors in numeric input fields
    if (elem.type === 'number') { return; }

    // For IE Only
    if (document.selection) {
        // Set focus
        elem.focus();
        // Use IE Ranges
        var oSel = document.selection.createRange();
        // Reset position to 0 & then set at end
        oSel.moveStart('character', -elemLen);
        oSel.moveStart('character', elemLen);
        oSel.moveEnd('character', 0);
        oSel.select();
    }
    else if (elem.selectionStart || elem.selectionStart == '0') {
        // Firefox/Chrome
        elem.selectionStart = elemLen;
        elem.selectionEnd = elemLen;
        elem.focus();
    } // if
} // SetCaretAtEnd()

$(document).ready(function(){
  $('div.api-not-available').show();
  $('div.api-messages').hide();

  page_bindings();
});

function page_bindings() {
  $(document).on('click', 'span.user-box input[type=button]#login', function(ev) {
    ev.preventDefault();
    register_creds();
  });

  $(document).on('keyup', 'span.user-box input', function(ev) {
    ev.preventDefault();
    if (ev.which !== 13) { return; }
    register_creds();
  });

  $(document).on('click', 'span.user-box img.logout.button', function(ev) {
    ev.preventDefault();
    connection.close();

    // this is done here so we don't disturb the user during momentary communication
    // failure with the API
    $('.zone-page').slideUp(function() {
      $('.zone-page.zone-data-summary>table>tbody').empty();
      $('.zone-page.zone-edit table.zone-records-table>tbody').empty();
      $('.zone-page.zone-edit span.zone-edit-meta-svalue').empty();
      $('.zone-page.zone-edit span.zone-edit-meta-value').empty();
      $('.zone-page.zone-edit li').remove();
    });
    $('span.user-box div.logged-in-profile').toggle('slide', function() {
      $.each(['department','username'], function(i,e) {
        $('span.user-box div.logged-in-profile span.'+e).empty();
      });
      $('span.user-box div.logged-in-profile span.userpic').css({backgroundImage:''});
    });
    document.cookie = 'cbtid'+'=; expires=Thu, 01 Jan 1970 00:00:01 GMT;';

    wamp_subscriptions={};
    fade_in_login();
  });

  $(document).on('click', '.location-bar li', function(ev){
    ev.preventDefault();

    // reset div visibilities
    $('.zone-page').hide();

    var navi = $(ev.target).text();

    var idxs = $.map($('.location-bar ul li'), function(e){
        return $(e).text();
    });

    var offt = idxs.indexOf(navi);

    $('.location-bar ul li').slice(offt+1).remove();

    if (navi === 'Home') {
      navi='zone-data-summary';
    } else {
      navi=navi.toLowerCase().replace(' ','-')
    }

    if (ev.originalEvent !== undefined) {
      $('.'+navi).show(200);
    }
  });

  // menu bar click callback
  $(document).on('click', '.menu-bar li', function(ev){
    var tgt = $(ev.target).text();

    console.info(tgt);
    if (tgt === 'Add zone') {
      show_butterfly_tools();
      zone_add(ev);
    }

    if (tgt == 'Tools') {
      show_butterfly_tools();
    }
  });

  // user selected a domain from the summary list
  $(document).on('click', '.zone-data-summary>table>tbody>tr', function(ev){
    var zone = $(ev.target).parent().children('td').first().next().text();

    zone_records_myzone = zone;

    $('.location-bar ul li').first().click();
    $('.location-bar ul').append('<li>Zone Edit</li>');

    $('.zone-edit-meta-value').html('');
    $('.zone-edit-meta-svalue').html('');
    $('.zone-edit p:contains("NS Glue")').next().children('ul').empty();
    $('.zone-edit-xfr-acl table tbody tr').remove();
    $('.zone-resource-records table tbody tr').remove();

    $('.zone-edit p:contains("SOA")').removeClass('dead');
    $('.zone-edit p:contains("Local")').removeClass('dead');
    $('.zone-edit p:contains("Registrar")').removeClass('dead');
    $('.zone-edit p:contains("NS Glue")').removeClass('dead');
    $('.zone-edit p:contains("Zone transfer ACL")').removeClass('dead');
    $('.zone-resource-records table thead th:last-child').removeClass('dead');

    $('.zone-edit p:contains("SOA")').addClass('loading');
    $('.zone-edit p:contains("Local")').addClass('loading');
    $('.zone-edit p:contains("Registrar")').addClass('loading');
    $('.zone-edit p:contains("NS Glue")').addClass('loading');
    $('.zone-edit p:contains("Zone transfer ACL")').addClass('loading');
    $('.zone-resource-records table thead th:last-child').addClass('loading');

    $('.zone-edit').show(200);

    var subs = {'records.get.local'             :zone_records_redraw_Local,
                'records.get.registrar'         :zone_records_redraw_Registrar,
                'records.get.ns_glue'           :zone_records_redraw_NS_Glue,
                'records.get.zone_transfer_acl' :zone_records_redraw_Zone_transfer_ACL,
                'records.get.resourcerecords'   :zone_records_redraw_Resource_Records,
                'records.get.single_rr'         :zone_records_redraw_Single_RR,
                'xfr-acls.get.single'           :zone_records_redraw_XFR_Single
               };

    var promises = []
    $.each(subs, function(uri_k,f) {
      var uri, p;
      uri = 'org.head.butterflydns.zone.'+uri_k+'.'+zone;
      p   = ss.subscribe(uri, f);
      wamp_subscriptions[uri] = f;
      promises.push(p);
    });

    // futile attempt to make the publishing happen asynchronously
    $.when(promises).done(function(res,err,progress) {
      //console.info(res,err,progress);

      if (err !== undefined ) {
        show_api_errors([err]);
      } else {
        setTimeout(function(){
          ss.call('org.head.butterflydns.zone.records.send',[zone]);
        }, 100);
      }
    });

    /*
    ss.call('org.head.butterflydns.zone.get_zone_glue',[zone], {}, {receive_progress:true}).then(
      function(res) {
        if (Object.keys(res)[0] === 'error') {
          console.log('omg',res);
          $('.zone-edit p:contains("NS Glue")').removeClass('loading').addClass('dead');
          return;
        }
        if (Object.keys(res)[0] === 'warning') {
          console.log('omg',res);
          $('.zone-edit p:contains("NS Glue")').removeClass('loading');
          return;
        }
        $('.zone-edit p:contains("NS Glue")').removeClass('loading');
      },

      function(err) {
        console.info('got err:',err);
        $('.zone-edit p:contains("NS Glue")').removeClass('loading').addClass('dead');
      },

      function (progress) {
        console.log("Progress:",progress);
      }
    );
    */

    ev.preventDefault();
  });

  // apply the changes on the meta sections (SOA, Local, Zone transfer ACL)
  $(document).on('click', '.zone-edit span.apply-changes', function(ev){
    ev.preventDefault();
    ev = $(ev.target);

    if (ev.parent()[0].nodeName === 'TD') {
      apply_records_table_changes(ev);
    } else {
      apply_changes(ev);
    }
  });

  // surely these can be rewritten to match any tables :)
  $(document).on('click', '.zone-data-summary>table>thead>tr>th:first-child>input', function(ev){
    var c = $(ev.target).prop('checked');
    $('.zone-data-summary>table>tbody>tr>td:first-child>input').prop('checked',c);
  });
  $(document).on('click', '.zone-resource-records>table>thead>tr>th:first-child>input', function(ev){
    var c = $(ev.target).prop('checked');
    $('.zone-resource-records>table>tbody>tr>td:first-child>input').prop('checked',c);
  });

  // start edit
  $(document).on('click', '.zone-records-table>tbody>tr>td', function(ev){
    ev.preventDefault();
    //console.log(ev);
    var tgt = $(ev.target);
    //figr=tgt;

    if (tgt.prop('nodeName') !== 'TD') {
      tgt = tgt.closest('td');
    }

    if (tgt.children().length >= 1 ) {
      // ignore clicks, this handler is for changing the table td's from text into inputs, NOT the checkbox/delete span
      return;
    }

    //fig = tgt;

    start_edit(tgt);
  });

  $(document).on('change', '.zone-template-editor>select#zone-template-names', function(ev){
    tgt = $(ev.target);
    console.log(ev);
    var idx = $('#zone-template-names option:selected').index();
    if (idx === 0) { return; }

    // all others will use the template input elements
    $('.zone-template-editor .template-box').slideDown();

    if (idx === 1) { template_new(); }
    // modify or delete
  });

  $(document).on('click', '.zone-edit-meta-value', function(ev){
    ev.preventDefault();

    // convert element data into input value
    if ($(ev.target).is("input")) {
      return;
    }

    var h = $(ev.target);
    var mailto=false;
    var oldvalue;

    if (h.children().is('a')){
      mailto=true;
      oldvalue = $(h.children('a')[0]).attr('oldvalue');
      h = $(h.children('a')[0]).text();
    } else {
      oldvalue = h.attr('oldvalue');
      h = h.text();
    }

    if (oldvalue === undefined) { oldvalue=h }

    if (mailto) {
        $(ev.target).html('<input type="text" oldvalue="'+oldvalue+'" value="'+h+'" mailto/>');
    } else {
        $(ev.target).html('<input type="text" oldvalue="'+oldvalue+'" value="'+h+'"/>');
    }

    var i = $(ev.target).children('input').first();
    i.focus();
    SetCaretAtEnd(i);

  });

  $(document).on('keyup', function(ev) {
    if (ev.ctrlKey === true && ev.which === 36) {
      // reload the home summary screen
      $('.zone-data-summary').show(200);
    }
  });

  $(document).on('focusout keyup mouseleave', '.zone-edit-meta-value, .zone-records-table', function(ev){
    var now = Date.now();


    if (!$(ev.target).is("input")) {
      return;
    }

    parent = $(ev.target).parent()[0].nodeName;
    //console.log(ev,parent);

    // multi element row
    if (ev.type === 'keyup') {
      if (parent === 'TD') {
        if (ev.which === 9) {      // ignore ESC and HTAB if parent object is TD
          return;
        }
      }

      // applies to all input types
      if (35 <= ev.which && ev.which <= 90) { // ignore normal characters on keyboard
        return;
      }

      if (93 <= ev.which && ev.which <= 111) { // ignore numpad
        return;
      }

      if (186 <= ev.which && ev.which <= 192) { // ignore: ; = , - . /
        return;
      }

      if (219 <= ev.which && ev.which <= 222) { // ignore: [ \ ] '
        return;
      }

      if ([16,17,18].indexOf(ev.which) > -1) {  // shift, ctrl, alt
        return
      }

      if (ev.which === 8 || ev.which === 32) {        // ignore backspace or space
        return;
      }

    } else {
      if (ev.type === 'mouseleave' || ev.type === 'focusout') {
        //console.log('ignoring event',ev);
        //recently_fired_events[ev.target] = now;
        //console.log('ignore mouseleave/focusout')
        return;
      }
    }

    //console.log('handling event',ev);


    //if (['mouseleave','mouseout','focusout'].indexOf(ev.type) > 1) {
    //  return;
    //}

    //if (!(ev.which === 27 || ev.which === 13 || ev.which === 9 || ev.type === 'mouseleave' || ev.type === 'mouseout' || ev.type === 'focusout')) {
      //console.info('ignoring as ev.which is ',ev.which);
    //  return;
    //}

    // filter out multiple events that happen inside 10 milliseconds
    if (ev.target in recently_fired_events) {
      if (recently_fired_events[ev.target] > now - 500) {
        return;
      } else {
        //console.log('ev delta is',now - recently_fired_events[ev.target]);
        delete recently_fired_events[ev.target];
      }
    }

    recently_fired_events[ev.target] = now;

    ev.preventDefault();
    ev = $(ev.target);
    var evp = ev.parent();

    figr=evp;

    if (evp[0].nodeName === 'TD') {
      // find the apply-changes button, switch to this as target
      ev = $(ev.closest('tr').find('span.apply-changes')[0]);
      apply_records_table_changes(ev);
    } else {
      stop_edit(ev);
      // ev is now an orphaned element that has been deleted
      set_unset_save_icon(evp);
    }
  });

  $(document).on('click', '.zone-edit span.delete-record', function(ev){
    ev.preventDefault();
    ev.stopImmediatePropagation();
    ev = $(ev.target);

    // fire off the row deletion from here

    if (ev.parent()[0].nodeName === 'TD') {
      apply_records_table_changes(ev);
      return;
    }
  });

  $(document).on('click', '.zone-edit span.revert-changes', function(ev){
    ev.preventDefault();
    ev.stopImmediatePropagation();
    ev = $(ev.target);

    if (ev.parent()[0].nodeName === 'TD') {
      apply_records_table_changes(ev);
      return;
    }

    // undo changes
    var e = ev.prev();
    var oldvalue = e.attr('oldvalue');

    if (e.children().is('a')){
      e.children('a').first().text(oldvalue);
      e.children('a').first().attr('href',oldvalue);
    } else {
      oldvalue = e.attr('oldvalue');
      e.text(oldvalue);
    }

    e.removeAttr('oldvalue');
    e.next('span.revert-changes').remove();
    sanity_check_soa_table();
    set_unset_save_icon(e);
  });

  $(document).on('click', 'span.add-record', function(ev){
    ev.preventDefault();

    // add a table to this row
    var evt = $(ev.target);
    var tb = evt.closest('table').find('tbody');
    var tdl = evt.closest('table').find('thead>tr').children('th').slice(1);
    var ntr = '<tr class="new-record"><td><input type="checkbox"/><span class="button-icon delete-record"></span></td>';

    $.each(tdl, function(n) { ntr+= '<td></td>'; });
    ntr += '</tr>';

    tb.append(ntr);
    start_edit(tb.children().last().children().first().next());
  });
}


/* WAMP authentication process
 *
 * page loads, connection.open() runs. the callback for connection.open() ensures the
 * login box is faded out when it starts up.
 *
 * if we have recently logged in, our browser will have a cookie and authentication
 * will happen automagically in the background, no challenge-response-authentication
 * needed.
 *
 * if no recent login however, connection.open() will return a challenge and our
 * connection.onchallenge callback (which is a function appropriately named onchallenge)
 * will fire.
 *
 * onchallenge will check to see if our login credentials are available in the input
 * elements. if not, it'll fade in the login box and halt the wamp connection attempt.
 *
 * when the user has entered their credentials, the page binding for the login element
 * will run register_creds which updates our connection parameters and restarts
 * connection.open again. this time everything will repeat but onchallenge will find
 * credentials in our connection paramenters.
 *
 * connection.onchallenge will then submit these values as a response to our challenge.
 *
 * assuming correct credentials, connection.open will then get login details, populate
 * the userbox with info, and slide it into view. subsequently we [re]store our known
 * subscriptions (zones we've edited in this session) then an RPC call is made to
 * trigger a summary of all of the zones being published to us.
 *
 */

// the WAMP connection to the Router
var connection = new autobahn.Connection({
  url: wsuri,
  realm: "butterflydns",
  authmethods: ['cookie','ticket'],
  authid: principal,
  onchallenge: onchallenge
});

// fired when a fully authenticated connection is established and session attached
connection.onopen = function (session, details) {
  fade_out_login();
  $('#api-na-content').html('Waiting for API ...');
  ss=session;

  if (details.authextra === undefined) {
    // cookie auth doesn't get any details from our authenticator, so fetch them
    // keep retrying if there's a problem
    function get_role_details() {
      session.call('org.head.butterflydns.role.lookup', [details.authid]).then(
        function(res) { draw_details(res.extra); ponderous_attach(); },
        function(err) { setTimeout(get_role_details, 5000); }
      );
    }

    get_role_details();
  } else {
    /* cred login comes back fully loaded */
    draw_details(details.authextra);
    ponderous_attach();
  }

  // this delay is to allow the login box to finish fading out before we slide in
  function draw_details(details) {
    setTimeout(function(d) {
      slide_in_profile(d);
    }, 750, details);
  }

  // if our API is busy sharting itself, wait until it cleans up
  function ponderous_attach() {
    // how we figure out this is a new page load -- no subscriptions!
    if (!('org.head.butterflydns.zones.summary' in wamp_subscriptions)) {
      wamp_subscriptions['org.head.butterflydns.zones.summary'] = redraw_zones_summary;
      wamp_subscriptions['org.head.butterflydns.zone.records.get.soa'] = zone_records_redraw_SOA;
      resubscribe();

      session.call('org.head.butterflydns.zones.summary.trigger').then(
          function (res) {
            $('.api-not-available').hide();
            $('.menu-bar li').css({opacity:'1.0'});
            $('.zone-page').css({opacity:1.0});
          },
          function (error) {
            setTimeout(ponderous_attach, 5000);
          }
      );

    } else {
      console.info('this is a reconnect, just resub it all');
      resubscribe();
      $('.api-not-available').hide();
      $('.menu-bar li').css({opacity:'1.0'});
      $('.zone-page').css({opacity:1.0});
    }
  }
}

// fired when connection was lost (or could not be established)
connection.onclose = function (reason, details) {
  console.log("Connection lost: " + reason);
  console.log(details);

  if (details.reason === 'wamp.error.authentication_failed') {
    console.log('uhm, shit?');
    $('span.user-box').addClass('auth_fail');
    $('#api-na-content').html('<br>Login needed');
  }

  $('.zone-page').css({opacity:.2});
  $('.api-not-available').show();
  $('.menu-bar li').css({opacity:'0.2'});
}

// if our connection.open() returns a challenge response, then
// this callback will be fired. our connection.open() will either:
//   a) succeed because of a cookie or,
//   b) return a challenge requiring a username and password
function onchallenge (session, method, extra) {
  //console.info('challenge received:', session, method, extra);

  if (method === "ticket") {
    // if there's no u/p login cred yet, fade in the login window
    // and ask the user to login. on cred submit, call connection.open()
    // initiator again
    var u,p;
    u = get_login_creds();
    p = u['p'], u = u['u'];

    if (u === undefined || u.length === 0 || p === undefined || p.length === 0) {
      fade_in_login();
      $('#api-na-content').html('<br>Login needed');
      connection.close();
    } else {
      return ticket;
    }
  } else {
    console.warn("i can't handle this challenge method!",method);
  }
}

// now actually open the connection
connection.open();

// copy our input element credential values to our global variables
function register_creds() {
  var u,p;
  u         = get_login_creds()
  ticket    = u['p'];
  principal = u['u'];

  $('span.user-box').removeClass('auth_fail');

  // this line is a workaround for a wamp-js bug. the authid gets lost :/
  console.info(connection._options.authid);
  connection._options.authid = principal;

  $('#api-na-content').html('<br>Logging in');
  connection.open();
}

function get_login_creds() {
  var u = $('span.user-box input#username').val(),
      p = $('span.user-box input#password').val();

  return {u, p};
}

// fade in the login is called when we need the user to input their credentials
function fade_in_login() {
  $('span.user-box').css({zIndex:102});
  $('span.user-box div.anonymous-login').slideDown(500, function() {
    $('span.user-box div.please-log-in').slideDown(500, function() {
      function fadeRunner(i) {
        if (i < 95) {
          $('span.user-box').css({'background-color':'rgba(224,240,255,'+i/100+')'});
          setTimeout(fadeRunner, 3, i+1);
        }
      }
      fadeRunner(0);
    });
  })
}

// we fade out the login as soon as the user has hit the login button
function fade_out_login() {
  function fadeRunner(i) {
    if (i > 0) {
      $('span.user-box').css({'background-color':'rgba(224,240,255,'+i/100+')'});
      setTimeout(fadeRunner, 3, i-1);
    }
  }
  fadeRunner(95);
  $('span.user-box div.please-log-in').slideUp(250)
  $('span.user-box').css({zIndex:100});
  $('span.user-box div.anonymous-login').slideUp(250);
}

function slide_in_profile(d) {
  $('span.user-box div.logged-in-profile').find('span.userpic').css({
    backgroundImage:'url(data:image/png;base64,'+d.jpegPhoto,
  })
  .parent().find('span.department').text(d.department)
  .parent().find('span.username').text(d.displayName)
  .parent().toggle('slide', {direction:'right'});
}

// we have to resubscribe to all of our subs if crossbar router is restarted
// invisible WTFness evidenced by published events never appearing to us
// surely our wamp module should handle that for us :P
function resubscribe() {
  var promises = [], p;
  $.each(wamp_subscriptions, function(uri,f) {
    p = ss.subscribe(uri, f);
    promises.push(p);
  });

  $.when(promises).done(function(res,err,progress) {
    //console.info(res,err,progress);
    if (err !== undefined ) {
      show_api_errors([err]);
    }
  });
}

function redraw_zones_summary (args) {
  var tdata = '';
  $('.zone-data-summary > table > tbody').empty();

  // this will also need to be updated gently, and we need to store the sql record ID
  // so we don't break any edits

  var trs=[];
  $.each(args[0], function(i, r) {
    var serial = r.soa.serial;
    trs.push('<tr>'+
         '<td><input type="checkbox"/><span class="button-icon delete-record"></span></td>'+
         '<td>'+r.zone+'</td>'+
         '<td>'+serial+'</td>'+
         '<td>'+r.manager+'</td>'+
         '<td>'+r.created.substr(0,21)+'</td>'+
         '<td>'+r.updated.substr(0,21)+'</td>'+
         '</tr>');
  });
  trs = trs.join('\n');
  $('.zone-data-summary > table > tbody').append(trs);

  if ($('.location-bar ul li').not('.permanent').length === 0) {
    // make sure the table is visible
    $('.zone-data-summary').show()
  }
}

// todo: gently rewrite this in case an edit is going on
// note: this fires on zone summary and zone records
function zone_records_redraw_SOA(args) {
  args = args[0];
  var z,
      ze      = $('.zone-edit p:contains("SOA")').next(),
      contact = '<a href="mailto:'+args.data.contact+'">'+args.data.contact+'</a>'

  //$('.zone-data-summary')
  var tr  = $('.zone-data-summary td:contains("'+args.zone+'")').closest('tr'),
      tds = tr.find('td');

  // update this row's serial, created, and updated
  if ($(tds[2]).text() !== ''+args.data.serial ||
      $(tds[4]).text() !== args.created     ||
      $(tds[5]).text() !== args.updated) {
    $(tds[2]).text(args.data.serial);
    $(tds[4]).text(args.created);
    $(tds[5]).text(args.updated);
    tr.find('td').addClass('updated');
  }

  // only update this page if args.zone == zone
  if (zone_records_myzone !== undefined && args.zone === zone_records_myzone) {
    z = ze.find('span:contains("Zone")').next();
    if (z.text() !== args.zone) { z.addClass('updated'); }
    z.text(args.zone);

    z = ze.find('span:contains("Default TTL")').next();
    if (z.text() !== ''+args.ttl) { z.addClass('updated'); }
    z.text(args.ttl);

    z = ze.find('span:contains("Primary NS")').next();
    if (z.text() !== args.data.primary_ns) { z.addClass('updated'); }
    z.text(args.data.primary_ns);

    z = ze.find('span:contains("Contact")').next();
    if (z.html() !== contact) { z.addClass('updated'); }
    z.html(contact);

    z = ze.find('span:contains("Serial")').next();
    if (z.text() !== ''+args.data.serial) { z.addClass('updated'); }
    z.text(args.data.serial);

    z = ze.find('span:contains("Refresh")').next();
    if (z.text() !== ''+args.data.refresh) { z.addClass('updated'); }
    z.text(args.data.refresh);

    z = ze.find('span:contains("Retry")').next();
    if (z.text() !== ''+args.data.retry) { z.addClass('updated'); }
    z.text(args.data.retry);

    z = ze.find('span:contains("Expire")').next();
    if (z.text() !== ''+args.data.expire) { z.addClass('updated'); }
    z.text(args.data.expire);

    z = ze.find('span:contains("Minimum TTL")').next();
    if (z.text() !== ''+args.data.minimumttl) { z.addClass('updated'); }
    z.text(args.data.minimumttl);

    $('.zone-edit p:contains("SOA")').removeClass('loading');
  }

  setTimeout(function() {
    ze.find('span.updated').removeClass('updated');
    tr.find('td').removeClass('updated');
  }, 2000);
}

// instead of doing ss.call(), subscribe to a wamp proceedure?
// todo: gently rewrite this in case an edit is going on
function zone_records_redraw_Local(args) {
  args = args[0];
  var z, ze = $('.zone-edit p:contains("Local")').next();

  if (zone_records_myzone.length && args.zone !== zone_records_myzone) { return; }
  z = ze.find('span:contains("Manager")').next();
  if (z.text() !== args.manager) { z.addClass('updated'); }
  z.text(args.manager);

  z = ze.find('span:contains("Owner")').next()
  if (z.text() !== args.owner) { z.addClass('updated'); }
  z.text(args.owner);

  ze.find('span:contains("Created")').next().text(args.created);
  ze.find('span:contains("Updated")').next().text(args.updated);

  $('.zone-edit p:contains("Local")').removeClass('loading');

  setTimeout(function() {
    ze.find('span.updated').removeClass('updated');
  }, 2000);
}

function zone_records_redraw_Registrar(args) {
  args = args[0];
  var ze = $('.zone-edit p:contains("Registrar")').next();

  //console.log(zone_records_myzone, args.zone);

  if (zone_records_myzone.length && args.zone !== zone_records_myzone) { return; }

  ze.find('span:contains("Registrar")').next().text(args.registrar);
  ze.find('span:contains("Status")').next().text(args.status);
  ze.find('span:contains("Created")').next().text(args.created);
  ze.find('span:contains("Updated")').next().text(args.updated);
  ze.find('span:contains("Expires")').next().text(args.expires);

  if (parseInt(args.expires.substr(21)) < 30) {
    console.warning('expires:',args.expires);
    ze.find('span:contains("Expires")').next().css({'background-color':'red'});
  }

  $('.zone-edit p:contains("Registrar")').removeClass('loading');
}

function zone_records_redraw_NS_Glue(args) {
  args = args[0];
  //console.log('redraw glue');
  //console.log(args);
  //console.log(zone_records_myzone,args.zone, zone_records_myzone == args.zone, zone_records_myzone === args.zone);
  var lis = [],
       ze = $('.zone-edit p:contains("NS Glue")').next();

  if (zone_records_myzone.length > 0 && args.zone !== zone_records_myzone) { return; }
  ze.children('ul').empty();

  $.each(args.data, function(n,e) {
    lis.push('<li class="zone-edit-meta-svalue">'+Object.keys(args.data[n])[0]+'<ul>');
    $.each(e, function(j,vl) {
      $.each(vl, function(k,v) {
        lis.push('<li>'+v+'</li>');
      });
    });
    lis.push('</ul></li>');
  });

  lis = lis.join('\n')

  $('.zone-edit p:contains("NS Glue")').next('div').children('ul').append(lis);

  $('.zone-edit p:contains("NS Glue")').removeClass('loading');
}

// todo: gently rewrite this in case an edit is going on
function zone_records_redraw_Zone_transfer_ACL(args) {
  args = args[0];
  var ze = $('.zone-edit-xfr-acl table tbody');

  if (zone_records_myzone.length > 0 && args.zone !== zone_records_myzone) { return; }
  ze.find('tr').remove();

  var trs = [];
  $.each(args.data, function(i, r) {
    trs.push('<tr rid="'+r.rid+'" title="'+'created: '+r.created+', updated: '+r.updated+'">'+
           '<td><input type="checkbox"/><span class="button-icon delete-record"></span></td>'+
           '<td>'+r.client+'</td>'+
           '</tr>');
  });
  trs = trs.join('\n');
  ze.append(trs);

  $('.zone-edit p:contains("Zone transfer ACL")').removeClass('loading');
}

function zone_records_redraw_Resource_Records(args) {
  args = args[0];

  //console.info('redraw RR',args);
  var tr = 0,
      ze = $('.zone-resource-records table tbody');

  // eventually we want to redraw this very gently, if someone is editing, this will
  // fuck up their edit -- might make them unhappy!
  //
  // this means updating all rows -but- this particular row

  // iterate through the records, keep track of our tr position in the table
  // for each data record, look for data[rid] in the table
  // if data[rid] is not in the table, insert a new row at index {tr}
  // if it is found in the table:
  //    if this rowid MATCHES the triggering rowid
  //        disregard this data row
  //    otherwise, if this row is NOT being edited
  //       if tr/td text()/val() is different from data
  //           update the text() add the class "updated" on the affected TD
  //    else
  //        highlight the entire row in red glow (the TDs)
  //        fly out a div that shows the changes the DB knows about
  //        let the user diff/apply

  if (zone_records_myzone !== undefined && args.zone !== zone_records_myzone) { return; }
  ze.find('tr').remove();

  var trs = [];
  $.each(args.data, function(i, r) {
      if (r.ttl === null) { r.ttl = ''; }
      trs.push('<tr rid="'+r.rid+'" title="'+'created: '+r.created+', updated: '+r.updated+'">'+
           '<td><input type="checkbox"/><span class="button-icon delete-record"></span></td>'+
           '<td>'+r.host+'</td>'+
           '<td>'+r.ttl+'</td>'+
           '<td>'+r.type+'</td>'+
           '<td>'+r.priority+'</td>'+
           '<td>'+r.data+'</td>'+
           '</tr>');
  });
  trs = trs.join('\n');
  ze.append(trs);

  $('.zone-resource-records table thead th:last-child').removeClass('loading');
}

// on zone selection, our UI expects a full list of records. this is for single row live updates
function zone_records_redraw_Single_RR(args) {
  args = args[0];

  //console.info('redraw SRR',args);
  if (zone_records_myzone !== undefined && args.zone !== zone_records_myzone) {console.info('goobye'); return; }

  setTimeout(function() {
    var tr       = 0,
        ze       = $('.zone-resource-records table tbody'),
        existing = $.map(ze.find('tr'), function(e) { if ($(e).attr('rid') === ''+args.rid) {return e;} });

    // check if being edited
    if($(existing).children().first().find('span.apply-changes').length) {
      console.log('ruh roh, collision!');
    }

    // see if this row id already exists or is new
    if (existing.length === 0) {
      if (args.ttl === null) { args.ttl = ''; }
      var nr = '<tr rid="'+args.rid+'">'+
             '<td><input type="checkbox"/><span class="button-icon delete-record"></span></td>'+
             '<td>'+args.host+'</td>'+
             '<td>'+args.ttl+'</td>'+
             '<td>'+args.type+'</td>'+
             '<td>'+args.priority+'</td>'+
             '<td>'+args.data+'</td>'+
             '</tr>';

      var tr = $(ze).append(nr).children().last();
      $(tr).children('td').addClass('updated');
      setTimeout(function() {
        $(tr).children('td').removeClass('updated');
      }, 2000);

    } else if ('host' in args) {
      var tds = $(existing).children('td');
      $(tds[1]).text(args.host);
      $(tds[2]).text(args.ttl);
      $(tds[3]).text(args.type);
      $(tds[4]).text(args.priority);
      $(tds[5]).text(args.data);

      $(existing).attr('title', 'created: '+timeConverter(args.created)+', updated: '+timeConverter(args.updated));
      $(existing).children('td').addClass('updated');

      setTimeout(function() {
        $(existing).children('td').removeClass('updated');
      }, 2000);
    } else {
      $.each($(existing).find('td'), function(i,e) {
        //if (i===0) { return; }
        $(e).addClass('deleted');
      });

      setTimeout(function() {
          $(existing).fadeOut(function(){
            $(existing).slideUp(function(){
              $(existing).remove();
            });
          });
        }, 2000);
    }
  }, 50);
}

function zone_records_redraw_XFR_Single(args) {
  args = args[0];

  if (zone_records_myzone.length > 0 && args.zone !== zone_records_myzone) { return; }

  // this callback happens too fast in some instances. our initial publish lands here before it stuffs the
  // RID into the row, so we end up creating a duplicate row, delay 200 milliseconds.
  // we need a locking mechanism as these delays are very prone to timing slew

  setTimeout(function() {
    var tr       = 0,
        ze       = $('.zone-edit-xfr-acl table tbody'),
        existing = $.map(ze.find('tr'), function(e) { if ($(e).attr('rid') === ''+args.rid) {return e;} });

    // check if being edited
    if($(existing).children().first().find('span.apply-changes').length) {
      console.log('ruh roh, collision!');
    }

    // see if this row id already exists or is new
    if (existing.length === 0) {
      if (args.ttl === null) { args.ttl = ''; }
      var nr = '<tr rid="'+args.rid+'">'+
             '<td><input type="checkbox"/><span class="button-icon delete-record"></span></td>'+
             '<td>'+args.host+'</td>'+
             '</tr>';

      var tr = $(ze).append(nr).children().last();
      $(tr).children('td').addClass('updated');
      setTimeout(function() {
        $(tr).children('td').removeClass('updated');
      }, 2000);

    } else if ('host' in args) {
      var tds = $(existing).children('td');
      $(tds[1]).text(args.host);
      $(existing).attr('title', 'created: '+timeConverter(args.created)+', updated: '+timeConverter(args.updated));

      $(existing).children('td').addClass('updated');

      setTimeout(function() {
        $(existing).children('td').removeClass('updated');
      }, 2000);
    } else {
      $.each($(existing).find('td'), function(i,e) {
        $(e).addClass('deleted');
      });

      setTimeout(function() {
          $(existing).fadeOut(function(){
            $(existing).slideUp(function(){
              $(existing).remove();
            });
          });
        }, 2000);
    }
  }, 50);
}

function zone_add(ev) {
  ev.preventDefault();
  $('html, body').animate({
    scrollTop: $(ev.target).offset().top
  }, "slow");
}

function show_butterfly_tools() {
  $('.zone-page').slideUp();
  // show mine
  $('.butterfly-tools').slideDown();

  // refresh template options
  ss.call('org.head.butterflydns.zone.template.names.get').then(
    function(res) {
      console.log('got data:',res);
      var sel = $('#zone-template-names');
      $('#zone-template-names option').slice(2).remove();
      $.each(res.names, function(i,e){
        console.log(e.name);
        sel.append('<option name="'+e.name+'" value="'+e.name+'">'+e.name+'</option>');
      });
    },
    function(err) {
      console.log('error',err);
    }
  );

}

function butterfly_settings() {
}

/* default template has no fields filled in
// required fields (SOA record and $TTL):
//   template name
//   nameserver (1+)
//   contact email address
//   $TTL (ttl column of the SOA record) (default is 21600)
//
// optional fields:
//   @ A or AAAA record
//   @ MX
//   www CNAME @
//
// sql schema:
//
CREATE SEQUENCE zone_template_rid_seq;
CREATE TABLE zone_templates (
  rid INT not null default nextval('zone_template_rid_seq'::regclass),
  name text,
  host text,
  ttl  int,
  type text,
  priority int,
  data text,
  created timestamp with time zone,
  updated timestamp with time zone
);

*/


function template_new(){
  div_templ = $('.zone-template-editor')
}
function template_modify(){
}
function template_delete(){
}

var figr;
var zone_records_myzone;

function apply_changes(ev) {
  console.info(ev);
  // get appropriate endpoint

  var endpoint = ev.prev().text().match(/[^:]+/)[0].toLowerCase().replace(/ /g,'_');

  // collect the data
  var data = {}, changed = [];

  // NOTE!!!! we need an indicator for which columns are changed
  // this is to track the updated field
  var sp = $(ev).parent().find('span.zone-edit-meta-value');
  var shit = $.each(sp, function(i,e) {
    var name = $(e).prev();
    var val  = $(e).text();
    if (name.length === 0) { name = 'ACL' } // axfr ACL
    else { name = $(name).text(); } // all other fields

    // a lot of single value arrays, but it's a common format
    if (name in data) { data[name].push(val); }
    else { data[name] = [val]; }

    if ($(e).attr('oldvalue') !== undefined) {
      changed.push(name);
    }
  });

  var zone = $('.zone-edit span:contains("Zone")').next('.zone-edit-meta-svalue').text();
  data['zone'] = zone;
  data['changed'] = changed;

  // rpc
  ev.prev().removeClass('dead');
  $('div.api-messages').slideUp().html('');
  ss.call('org.head.butterflydns.zone.meta.update', [data]).then(
    function(res) {
      if (res['success'] === true) {
        // remove all oldvalues attrs and the revert span
        $.each(sp, function(i,e) {
          $(e).removeAttr('oldvalue');
          $(e).next('span.revert-changes').remove();
        });
        // remove save icon
        ev.remove();
      } else {
        console.log(ev);
        show_api_errors(res['errors']);
        ev.prev().addClass('dead');
      }
    },
    function(err) {
      console.log(err);
      show_api_errors([err]);
      ev.prev().addClass('dead');
    },
    function(prg) {console.log(prg);}
  );
}

function show_api_errors(errors) {
  var h = $.map(errors, function(v) {
    return '<li>'+v+'</li>';
  });

  h.unshift('<ul>');
  h.push('</ul>');
  h = h.join('\n');

  $('div.api-messages>div').html(h);
  $('div.api-messages').slideDown();
}

function start_edit(tgt) {
  var ths = tgt.closest('table').children('thead').find('th');
  var tds = tgt.closest('tr').children();

  // replace the checkbox/trashcan with an ack/nack
  var td0 = $(tds[0]);
  td0.html('<span class="button-icon apply-changes"></span><span class="button-icon revert-changes"></span>');

  // make the following fields input text boxes:           record, data
  var text = ['Host','Record','Data','Remote clients'];
  // make the following fields input text boxes (numeric): ttl, priority
  var numeric = ['TTL','Priority'];
  // make the following fields select boxes:               type
  var select = ['Type'];

  $.each(tds, function(i,e) {
    var tv        = $(ths[i]).text(),
        oldvalue  = $(tds[i]).attr('oldvalue'),
        elemvalue = $(tds[i]).text();

    if (oldvalue === undefined) { oldvalue = elemvalue };

    if (text.indexOf(tv) > -1) {
      $(tds[i]).html('<input type="text" oldvalue="'+oldvalue+'" value="'+elemvalue+'" />');

    } else if (numeric.indexOf(tv) > -1) {
      $(tds[i]).html('<input type="number" oldvalue="'+oldvalue+'" value="'+elemvalue+'" />');

    } else if (select.indexOf(tv) > -1) {
      var __ = [], ___;
      __.push('<select oldvalue="'+oldvalue+'">');
      ___ = $.map(rtypes, function(v) {
        if (oldvalue === v) {
          return '<option value="'+v+'" selected>'+v+'</option>';
        } else {
          return '<option value="'+v+'">'+v+'</option>';
        }
      });
      __ = __.concat(___);
      __.push('</select>');

      $(tds[i]).html(__.join(''));

    }
  });

  // focus on the wanted input element
  var e=tgt.find('input')[0];
  e.focus();
  SetCaretAtEnd(e);
}

// convert zone record input values back into td text
function apply_records_table_changes(evt){
  var klass = evt.attr('class');
  var tname = evt.closest('div[class^="zone-edit-"]').attr('class');
  var endpoint, tds, ths;

  if (tname === 'zone-edit-xfr-acl') {
    endpoint='xfr-acl'
  } else {
    endpoint='record'
  }

  tds   = evt.closest('tr').children();
  ths   = $.map(evt.closest('table').children('thead').find('th'), function(e,i) { if (i>0) {return $(e).text().toLowerCase();} })

  ths.unshift('rid');
  ths[1]='host';

  if (klass.indexOf('apply-changes')>=0) {
    if (evt.closest('tr').hasClass('new-record')) {
      // push new record
      $('div.api-messages').slideUp();

      var vals = {};
      $.each(tds, function(i,e) {
        if (i === 0) { vals['rid']=$(e).parent().attr('rid'); }
        else         { vals[ths[i]] = $(e).children().first().val(); }
      });

      vals['zone'] = $($('.zone-edit-meta-svalue')[0]).text();

      ss.call('org.head.butterflydns.zone.'+endpoint+'.add', [vals]).then(
        function (res) {
          // do this fast so our apply_single_row function doesn't find a row
          // without this ID in it
          //console.info('result is',res);
          $(tds[0]).parent().attr('rid',res['rid']);
          //console.log("add_record() result:", res);
          evt.closest('tr').removeClass('new-record');
          // now set all the values
          $.each(tds, function(i,e) {
            if (i===0) { return; }
            var v = $($(e).children()[0]).val();

            $(tds[i]).html(v);
            $(tds[i]).attr('oldvalue',v);
          });
          $(tds[0]).html('<input type="checkbox"/><span class="button-icon delete-record"></span>');
        },
        function (err) {
          console.log("update_record() error:", err);
          show_api_errors(err.args);
        }
      );
    } else {
      // push to database
      $('div.api-messages').slideUp();

      var vals = {}, nvals = {}, ovals = {};
      $.each(tds, function(i,e) {
        if (i === 0) { vals['rid']=$(e).parent().attr('rid'); }
        else         { vals[ths[i]] = $(e).children().first().val(); }
      });

      vals['zone'] = $($('.zone-edit-meta-svalue')[0]).text();

      ss.call('org.head.butterflydns.zone.'+endpoint+'.update', [vals]).then(
        function (res) {
          //console.log("update_record() result:", res);
          // now convert all the input values back to text()
          $.each(tds, function(i,e) {
            if (i===0) { return; }
            var v = $($(e).children()[0]).val();

            $(tds[i]).html(v);
            $(tds[i]).attr('oldvalue',v);
          });

          $(tds[0]).html('<input type="checkbox"/><span class="button-icon delete-record"></span>');

        },
        function (err) {
          console.log("update_record() error:", err);
          show_api_errors(err.args);
        }
      );
    }
  } else if (klass.indexOf('revert-changes')>=0) {
    // void out a new unsaved record?
    if (evt.closest('tr').hasClass('new-record')) {
      //console.log('just delete this row');
      evt.closest('tr').remove();
      return;
    }
    // undo changes
    $.each(tds, function(i,e) {
      if (i===0) { return; }
      var v = $($(e).children()[0]).val(),
          oldvalue = $($(e).children()[0]).attr('oldvalue');

      if (v !== oldvalue) {
        v = oldvalue;
      }
      $(tds[i]).html(v);
    });
    $(tds[0]).html('<input type="checkbox"/><span class="button-icon delete-record"></span>');

  } else if (klass.indexOf('delete-record')>=0) {
    // we only need to send the zone and RID
    var vals = {  rid: $(evt).closest('tr').attr('rid'),
                 zone: $($('.zone-edit-meta-svalue')[0]).text() };

    $('div.api-messages').slideUp();
    ss.call('org.head.butterflydns.zone.'+endpoint+'.delete', [vals]).then(
      function (res) {
        //console.log("zone_record_delete() result:", res);
        //console.log("we let the redraw callback delete this row");
      },
      function (err) {
        console.log("update_record() error:", err);
        show_api_errors(err.args);
      }
    );
  }
}

// this applies to a single input element
function stop_edit(ev) {
  // convert element input back into element
  var mailto   = ev.attr('mailto');
  var oldvalue = ev.attr('oldvalue');
  var val      = ev.val();
  var isdiff   = false;

  if (val !== oldvalue) { isdiff=true; }

  var x;
  if (mailto !== undefined) {
    x = ev.parent().empty().append('<a href="mailto:'+val+'">'+val+'</a>');
  } else {
    x = ev.parent().empty().text(val);
  }

  if (isdiff) {
    x.attr('oldvalue',oldvalue);
    if (x.next('span.revert-changes').length === 0) {
      x.after('<span class="button-icon revert-changes"></span>');
    }
  } else {
    x.removeAttr('oldvalue');
    x.next('span.revert-changes').remove();
  }

  if (x.parent().parent().find('p').text() === 'SOA:') {
    sanity_check_soa_table();
  }
}

function set_unset_save_icon(el) {
  // step back, check all the inputs, if has attribute oldvalue, put the save icon up
  el = $(el);
  var isdiff = false,
      sp = el.closest('div').find('span.zone-edit-meta-value');

  // ignore multiple changes
  if (el.closest('div').parent().find('p').next('span.apply-changes').length > 0) { return; }

  $.each(sp, function(i,e) {
    if ($(e).attr('oldvalue') !== undefined) { isdiff=true; }
  });

  if (isdiff) {
    el.closest('div').parent().find('p').after('<span class="button-icon apply-changes"/>');
  } else {
    el.closest('div').parent().find('.apply-changes').remove();
  }
}

function sanity_check_soa_table() {
  // sanity check the numbers, only called for the SOA table
  spans = $('.zone-edit p:contains("SOA:")').next().find('span.zone-edit-meta-name');

  $.each(spans, function(i,e) {
    sv = $(e).next();

    var pname = $(e).text();

    if (['Default TTL','Serial','Refresh','Retry','Expire','Minimum TTL'].indexOf(pname) > -1) {
      if (pname === 'Serial') {
        nmax = 4294967295;
      } else {
        nmax = 2147483647;
      }

      var n = parseInt(sv.text());
      if (0 > n || n > nmax) {
        console.log('n',n,'nmax',nmax);
        sv.addClass('error');
      } else {
        sv.removeClass('error');
      }
    }

  });
}
