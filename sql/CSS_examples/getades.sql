/*
 *   GETADES -- SQL to recreate ADES similar to MPC Explorer
 *
 *   Usage: sudo -u postgres psql -A -t -q -v id="'448972'" -f <this file> -h sibyl mpc_sbn > <output file>
 *
 *   id is an unpacked permID (number) or a packed provID
 *
 *   R. Seaman, Mar 1, 2025
 */

select
  concat(
    concat('<?xml version="1.0" encoding="UTF-8"?>',E'\n'),
    '<ades version="2022">')
  ;

select
  concat(
    concat('  <optical>',E'\n'),
    case when permid   is not null then concat('    <permID>',permid,'</permID>',E'\n') end,
    case when provid   is not null then concat('    <provID>',provid,'</provID>',E'\n') end,
    case when trksub   is not null then concat('    <trkSub>',trksub,'</trkSub>',E'\n') end,
    case when obsid    is not null then concat('    <obsID>',obsid,'</obsID>',E'\n') end,
    case when trkid    is not null then concat('    <trkID>',trkid,'</trkID>',E'\n') end,
    case when trkmpc   is not null then concat('    <trkMPC>',trkmpc,'</trkMPC>',E'\n') end,
    case when mode     is not null then concat('    <mode>',mode,'</mode>',E'\n') end,
    case when stn      is not null then concat('    <stn>',stn,'</stn>',E'\n') end,
    case when sys      is not null then concat('    <sys>',sys,'</sys>',E'\n') end,
    case when ctr      is not null then concat('    <ctr>',ctr,'</ctr>',E'\n') end,
    case when pos1     is not null then concat('    <pos1>',pos1,'</pos1>',E'\n') end,
    case when pos2     is not null then concat('    <pos2>',pos2,'</pos2>',E'\n') end,
    case when pos3     is not null then concat('    <pos3>',pos3,'</pos3>',E'\n') end,
    case when prog     is not null then concat('    <prog>',prog,'</prog>',E'\n') end,
    case when obstime  is not null then concat('    <obsTime>',to_json(obstime)#>>'{}','Z</obsTime>',E'\n') end,
    case when rmstime  is not null then concat('    <rmsTime>',rmstime,'</rmsTime>',E'\n') end,
    case when ra       is not null then concat('    <ra>',ra,'</ra>',E'\n') end,
    case when dec      is not null then concat('    <dec>',dec,'</dec>',E'\n') end,
    case when rmsra    is not null then concat('    <rmsRA>',rmsra,'</rmsRA>',E'\n') end,
    case when rmsdec   is not null then concat('    <rmsDec>',rmsdec,'</rmsDec>',E'\n') end,
    case when rmscorr  is not null then concat('    <rmsCorr>',rmscorr,'</rmsCorr>',E'\n') end,
    case when astcat   is not null then concat('    <astCat>',astcat,'</astCat>',E'\n') end,
    case when mag      is not null then concat('    <mag>',mag,'</mag>',E'\n') end,
    case when rmsmag   is not null then concat('    <rmsMag>',rmsmag,'</rmsMag>',E'\n') end,
    case when band     is not null then concat('    <band>',band,'</band>',E'\n') end,
    case when photcat  is not null then concat('    <photCat>',photcat,'</photCat>',E'\n') end,
    case when photap   is not null then concat('    <photAp>',photap,'</photAp>',E'\n') end,
    case when logsnr   is not null then concat('    <logSNR>',logsnr,'</logSNR>',E'\n') end,
    case when seeing   is not null then concat('    <seeing>',seeing,'</seeing>',E'\n') end,
    case when exp      is not null then concat('    <exp>',exp,'</exp>',E'\n') end,
    case when rmsfit   is not null then concat('    <rmsFit>',rmsfit,'</rmsFit>',E'\n') end,
    case when nstars   is not null then concat('    <nStars>',nstars,'</nStars>',E'\n') end,
    case when ref      is not null then concat('    <ref>',ref,'</ref>',E'\n') end,
    case when disc     is not null then concat('    <disc>',disc,'</disc>',E'\n') end,
    case when subfmt   is not null then concat('    <subFmt>',subfmt,'</subFmt>',E'\n') end,
    case when prectime is not null then concat('    <precTime>',prectime,'</precTime>',E'\n') end,
    case when precra   is not null then concat('    <precRA>',precra,'</precRA>',E'\n') end,
    case when precdec  is not null then concat('    <precDec>',precdec,'</precDec>',E'\n') end,
    case when notes    is not null then concat('    <notes>',notes,'</notes>',E'\n') end,
    case when remarks  is not null then concat('    <remarks>',remarks,'</remarks>',E'\n') end,
    case when unctime  is not null then concat('    <uncTime>',unctime,'</uncTime>',E'\n') end,
    '  </optical>'
  )

from
  obs_sbn

where
  permid in (:id)

and
  deprecated is null

and
  status in ('P','p')

order by
  obstime;

select
  concat(
    concat('  <optical>',E'\n'),
    case when permid   is not null then concat('    <permID>',permid,'</permID>',E'\n') end,
    case when provid   is not null then concat('    <provID>',provid,'</provID>',E'\n') end,
    case when trksub   is not null then concat('    <trkSub>',trksub,'</trkSub>',E'\n') end,
    case when obsid    is not null then concat('    <obsID>',obsid,'</obsID>',E'\n') end,
    case when trkid    is not null then concat('    <trkID>',trkid,'</trkID>',E'\n') end,
    case when trkmpc   is not null then concat('    <trkMPC>',trkmpc,'</trkMPC>',E'\n') end,
    case when mode     is not null then concat('    <mode>',mode,'</mode>',E'\n') end,
    case when stn      is not null then concat('    <stn>',stn,'</stn>',E'\n') end,
    case when sys      is not null then concat('    <sys>',sys,'</sys>',E'\n') end,
    case when ctr      is not null then concat('    <ctr>',ctr,'</ctr>',E'\n') end,
    case when pos1     is not null then concat('    <pos1>',pos1,'</pos1>',E'\n') end,
    case when pos2     is not null then concat('    <pos2>',pos2,'</pos2>',E'\n') end,
    case when pos3     is not null then concat('    <pos3>',pos3,'</pos3>',E'\n') end,
    case when prog     is not null then concat('    <prog>',prog,'</prog>',E'\n') end,
    case when obstime  is not null then concat('    <obsTime>',to_json(obstime)#>>'{}','Z</obsTime>',E'\n') end,
    case when rmstime  is not null then concat('    <rmsTime>',rmstime,'</rmsTime>',E'\n') end,
    case when ra       is not null then concat('    <ra>',ra,'</ra>',E'\n') end,
    case when dec      is not null then concat('    <dec>',dec,'</dec>',E'\n') end,
    case when rmsra    is not null then concat('    <rmsRA>',rmsra,'</rmsRA>',E'\n') end,
    case when rmsdec   is not null then concat('    <rmsDec>',rmsdec,'</rmsDec>',E'\n') end,
    case when rmscorr  is not null then concat('    <rmsCorr>',rmscorr,'</rmsCorr>',E'\n') end,
    case when astcat   is not null then concat('    <astCat>',astcat,'</astCat>',E'\n') end,
    case when mag      is not null then concat('    <mag>',mag,'</mag>',E'\n') end,
    case when rmsmag   is not null then concat('    <rmsMag>',rmsmag,'</rmsMag>',E'\n') end,
    case when band     is not null then concat('    <band>',band,'</band>',E'\n') end,
    case when photcat  is not null then concat('    <photCat>',photcat,'</photCat>',E'\n') end,
    case when photap   is not null then concat('    <photAp>',photap,'</photAp>',E'\n') end,
    case when logsnr   is not null then concat('    <logSNR>',logsnr,'</logSNR>',E'\n') end,
    case when seeing   is not null then concat('    <seeing>',seeing,'</seeing>',E'\n') end,
    case when exp      is not null then concat('    <exp>',exp,'</exp>',E'\n') end,
    case when rmsfit   is not null then concat('    <rmsFit>',rmsfit,'</rmsFit>',E'\n') end,
    case when nstars   is not null then concat('    <nStars>',nstars,'</nStars>',E'\n') end,
    case when ref      is not null then concat('    <ref>',ref,'</ref>',E'\n') end,
    case when disc     is not null then concat('    <disc>',disc,'</disc>',E'\n') end,
    case when subfmt   is not null then concat('    <subFmt>',subfmt,'</subFmt>',E'\n') end,
    case when prectime is not null then concat('    <precTime>',prectime,'</precTime>',E'\n') end,
    case when precra   is not null then concat('    <precRA>',precra,'</precRA>',E'\n') end,
    case when precdec  is not null then concat('    <precDec>',precdec,'</precDec>',E'\n') end,
    case when notes    is not null then concat('    <notes>',notes,'</notes>',E'\n') end,
    case when remarks  is not null then concat('    <remarks>',remarks,'</remarks>',E'\n') end,
    case when unctime  is not null then concat('    <uncTime>',unctime,'</uncTime>',E'\n') end,
    '  </optical>'
  )

from
  obs_sbn

where
  permid is null

and
  provid

in
  (select
    unpacked_secondary_provisional_designation
  from
    current_identifications
  where
    packed_primary_provisional_designation in (:id)
  )

and
  deprecated is null

and
  status in ('P','p')

order by
  obstime;

select '</ades>';
