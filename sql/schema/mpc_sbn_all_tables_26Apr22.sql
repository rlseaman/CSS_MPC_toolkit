/*

CURRENT MPC/SBN LOGICAL REPLICATION TABLE CREATE SCRIPTS
INCLUDING COLUMN COMMENTS AND SELECTED INDEXES

NB: For faster subscription creation, consider creating 'obs_sbn' table 
indices (concurrently) AFTER subscription initialization.

(drop table syntax included but commented out)


 Source Server         : AWS_MPC_SBN_LOOPBACK
 Source Server Type    : PostgreSQL
 Source Server Version : 180003 (180003)
 Source Host           : AWS_MPC_SBN_LOOPBACK
 Source Catalog        : mpc_sbn_test
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 180003 (180003)
 File Encoding         : 65001

 Date: 19/03/2026 10:26:06
*/


-- ----------------------------
-- Table structure for comet_names
-- ----------------------------
--DROP TABLE IF EXISTS "public"."comet_names";
CREATE TABLE "public"."comet_names" (
  "id" int4 NOT NULL,
  "packed_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "name" text COLLATE "pg_catalog"."default",
  "naming_publication_references" text[] COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."comet_names" OWNER TO "postgres";
COMMENT ON COLUMN "public"."comet_names"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."comet_names"."packed_primary_provisional_designation" IS 'Packed form of the primary provisional designation (e.g. J81E29H ).';
COMMENT ON COLUMN "public"."comet_names"."unpacked_primary_provisional_designation" IS 'Unpacked form of the primary provisional designation (e.g. 1981 EH29).';
COMMENT ON COLUMN "public"."comet_names"."name" IS 'Comet name (UTF-8)';
COMMENT ON COLUMN "public"."comet_names"."naming_publication_references" IS 'Publication references to WGSBN or MPC.';
COMMENT ON COLUMN "public"."comet_names"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."comet_names"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."comet_names" IS 'List of COMET primary provisional designations (packed and unpacked) and their names and publication references';

-- ----------------------------
-- Table structure for current_identifications
-- ----------------------------
--DROP TABLE IF EXISTS "public"."current_identifications";
CREATE TABLE "public"."current_identifications" (
  "id" int4 NOT NULL,
  "packed_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "packed_secondary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_secondary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "published" int4,
  "identifier_ids" text[] COLLATE "pg_catalog"."default" NOT NULL,
  "object_type" int4,
  "numbered" bool,
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."current_identifications" OWNER TO "postgres";
COMMENT ON COLUMN "public"."current_identifications"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."current_identifications"."packed_primary_provisional_designation" IS 'Packed form of the primary provisional designation (e.g. K17P08M).';
COMMENT ON COLUMN "public"."current_identifications"."packed_secondary_provisional_designation" IS 'Packed form of one of the secondary provisional designations (e.g. K06Sf5M).';
COMMENT ON COLUMN "public"."current_identifications"."unpacked_primary_provisional_designation" IS 'Unpacked form of the primary provisional designation (e.g. 2017 PM8).';
COMMENT ON COLUMN "public"."current_identifications"."unpacked_secondary_provisional_designation" IS 'Unpacked form of one of the secondary provisional designations (e.g. 2006 SM415).';
COMMENT ON COLUMN "public"."current_identifications"."published" IS 'Integer describing the publication status of the identification: 0=not published, 1=published in an MPEC, 2=published in the DOU, 3=published in a mid-month circular, 4=published in a monthly circular';
COMMENT ON COLUMN "public"."current_identifications"."identifier_ids" IS 'List of unique identifiers used by the MPC to track credit for correct identifications ';
COMMENT ON COLUMN "public"."current_identifications"."object_type" IS 'Object classification based on its orbital element. For more information please see https://url.usb.m.mimecastprotect.com/s/9FytCnGWL0cxQOm2xUJhpTJmToG?domain=minorplanetcenter.net';
COMMENT ON COLUMN "public"."current_identifications"."numbered" IS 'Flag indicating if the primary designation is also numbered (True if it numbered, False if it is not numbered)';
COMMENT ON COLUMN "public"."current_identifications"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."current_identifications"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."current_identifications" IS 'All single-designations, and all identifications between designations. Always uses primary provisional designation (even for numbered objects). Includes all comets and satellites.';

-- ----------------------------
-- Table structure for minor_planet_names
-- ----------------------------
--DROP TABLE IF EXISTS "public"."minor_planet_names";
CREATE TABLE "public"."minor_planet_names" (
  "id" int4 NOT NULL,
  "mp_number" text COLLATE "pg_catalog"."default" NOT NULL,
  "name" text COLLATE "pg_catalog"."default" NOT NULL,
  "reference" text COLLATE "pg_catalog"."default" NOT NULL,
  "citation" text COLLATE "pg_catalog"."default",
  "discoverers" json,
  "created_at" timestamp(6),
  "updated_at" timestamp(6)
)
;
ALTER TABLE "public"."minor_planet_names" OWNER TO "postgres";
COMMENT ON COLUMN "public"."minor_planet_names"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."minor_planet_names"."mp_number" IS 'Unpacked permanent designation (e.g. 101955)';
COMMENT ON COLUMN "public"."minor_planet_names"."name" IS 'Minor planet name (UTF-8)';
COMMENT ON COLUMN "public"."minor_planet_names"."reference" IS 'Publication references to WGSBN or MPC.';
COMMENT ON COLUMN "public"."minor_planet_names"."citation" IS 'Citation associated with the name (the citation field can be null).';
COMMENT ON COLUMN "public"."minor_planet_names"."discoverers" IS 'List of discoverers in JSON format (the discoverers field can be null)';
COMMENT ON COLUMN "public"."minor_planet_names"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."minor_planet_names"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for mpc_orbits
-- ----------------------------
--DROP TABLE IF EXISTS "public"."mpc_orbits";
CREATE TABLE "public"."mpc_orbits" (
  "id" int4 NOT NULL,
  "packed_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "mpc_orb_jsonb" jsonb,
  "created_at" timestamp(6),
  "updated_at" timestamp(6),
  "orbit_type_int" int4,
  "u_param" int4,
  "nopp" int4,
  "arc_length_total" float8,
  "arc_length_sel" float8,
  "nobs_total" int4,
  "nobs_total_sel" int4,
  "a" float8,
  "q" float8,
  "e" float8,
  "i" float8,
  "node" float8,
  "argperi" float8,
  "peri_time" float8,
  "yarkovsky" float8,
  "srp" float8,
  "a1" float8,
  "a2" float8,
  "a3" float8,
  "dt" float8,
  "mean_anomaly" float8,
  "period" float8,
  "mean_motion" float8,
  "a_unc" float8,
  "q_unc" float8,
  "e_unc" float8,
  "i_unc" float8,
  "node_unc" float8,
  "argperi_unc" float8,
  "peri_time_unc" float8,
  "yarkovsky_unc" float8,
  "srp_unc" float8,
  "a1_unc" float8,
  "a2_unc" float8,
  "a3_unc" float8,
  "dt_unc" float8,
  "mean_anomaly_unc" float8,
  "period_unc" float8,
  "mean_motion_unc" float8,
  "epoch_mjd" float8,
  "h" float8,
  "g" float8,
  "not_normalized_rms" float8,
  "normalized_rms" float8,
  "earth_moid" float8,
  "fitting_datetime" timestamp(6),
  "updated_at_aws" timestamp(6)
)
;
ALTER TABLE "public"."mpc_orbits" OWNER TO "postgres";
COMMENT ON COLUMN "public"."mpc_orbits"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."mpc_orbits"."packed_primary_provisional_designation" IS 'Packed form of the primary provisional designation (e.g. K17P08M).';
COMMENT ON COLUMN "public"."mpc_orbits"."unpacked_primary_provisional_designation" IS 'Unpacked form of the primary provisional designation (e.g. 2017PM8).';
COMMENT ON COLUMN "public"."mpc_orbits"."mpc_orb_jsonb" IS 'MPC JSON format used to describe MPC orbits. The public python package is available as part of the MPC public Gitub https://url.usb.m.mimecastprotect.com/s/99S0CoAWMof8JqvR8FVi3Tprzm9?domain=github.com with additional information. ';
COMMENT ON COLUMN "public"."mpc_orbits"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."mpc_orbits"."updated_at" IS 'Date and time of latest row update';
COMMENT ON COLUMN "public"."mpc_orbits"."orbit_type_int" IS 'Orbit classification based on the object orbital element. For more information please see https://url.usb.m.mimecastprotect.com/s/EpyICp9WNpfyPMAWytGsBTGcgJ1?domain=minorplanetcenter.net';
COMMENT ON COLUMN "public"."mpc_orbits"."u_param" IS 'MPC defined U parameter. For more information please see https://url.usb.m.mimecastprotect.com/s/WCAkCqAWOqfRG0X3RsNtvTEHSvG?domain=minorplanetcenter.net. ';
COMMENT ON COLUMN "public"."mpc_orbits"."nopp" IS 'MPC computed number of oppositions. ';
COMMENT ON COLUMN "public"."mpc_orbits"."arc_length_total" IS 'Arc length of all the observations associated to the object, computed as the difference between the time of the last observations and the time of the first observation. ';
COMMENT ON COLUMN "public"."mpc_orbits"."arc_length_sel" IS 'Arc length of all the observations selected by the fit, computed as the difference between the time of the last selected observations and the time of the first selected observation. ';
COMMENT ON COLUMN "public"."mpc_orbits"."nobs_total" IS 'Total number of observations associated to the object.';
COMMENT ON COLUMN "public"."mpc_orbits"."nobs_total_sel" IS 'Total number of observations used by the fit. ';
COMMENT ON COLUMN "public"."mpc_orbits"."a" IS 'Semi-major axis [au]';
COMMENT ON COLUMN "public"."mpc_orbits"."q" IS 'Perihelion distance [au]';
COMMENT ON COLUMN "public"."mpc_orbits"."e" IS 'Eccentricity ';
COMMENT ON COLUMN "public"."mpc_orbits"."i" IS 'Inclination [degrees]';
COMMENT ON COLUMN "public"."mpc_orbits"."node" IS 'Longitude of the ascending node [degrees]';
COMMENT ON COLUMN "public"."mpc_orbits"."argperi" IS 'Argument of the pericenter [degrees]';
COMMENT ON COLUMN "public"."mpc_orbits"."peri_time" IS 'Time of the passage at the pericenter [days]';
COMMENT ON COLUMN "public"."mpc_orbits"."yarkovsky" IS 'A2 component of the Yarkovsky acceleration [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."srp" IS 'Solar radiation pressure [m^2/ton]';
COMMENT ON COLUMN "public"."mpc_orbits"."a1" IS 'A1 component of the non-gravitational acceleration for comets [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."a2" IS 'A2 component of the non-gravitational acceleration for comets [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."a3" IS 'A3 component of the non-gravitational acceleration for comets [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."dt" IS 'DeltaT component of the non-gravitational acceleration [days]';
COMMENT ON COLUMN "public"."mpc_orbits"."mean_anomaly" IS 'Mean anomaly [degrees]';
COMMENT ON COLUMN "public"."mpc_orbits"."period" IS 'Orbital period [days]';
COMMENT ON COLUMN "public"."mpc_orbits"."mean_motion" IS 'Orbital mean motion [degrees per day]';
COMMENT ON COLUMN "public"."mpc_orbits"."a_unc" IS 'Post-fit 1-sigma uncertainty in the semi-major axis [au] ';
COMMENT ON COLUMN "public"."mpc_orbits"."q_unc" IS 'Post-fit 1-sigma uncertainty in the perihelion distance [au] ';
COMMENT ON COLUMN "public"."mpc_orbits"."e_unc" IS 'Post-fit 1-sigma uncertainty in the eccentricity ';
COMMENT ON COLUMN "public"."mpc_orbits"."i_unc" IS 'Post-fit 1-sigma uncertainty in the inclination [degrees] ';
COMMENT ON COLUMN "public"."mpc_orbits"."node_unc" IS 'Post-fit 1-sigma uncertainty in the longitude of the node [degrees] ';
COMMENT ON COLUMN "public"."mpc_orbits"."argperi_unc" IS 'Post-fit 1-sigma uncertainty in the argument of the pericenter [degrees] ';
COMMENT ON COLUMN "public"."mpc_orbits"."peri_time_unc" IS 'Post-fit 1-sigma uncertainty in the time of the pericenter passage [days] ';
COMMENT ON COLUMN "public"."mpc_orbits"."yarkovsky_unc" IS 'Post-fit 1-sigma uncertainty in the A2 component of the Yarkovsky acceleration [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."srp_unc" IS 'Post-fit 1-sigma uncertainty in the solar radiation pressure [m^2/ton]';
COMMENT ON COLUMN "public"."mpc_orbits"."a1_unc" IS 'Post-fit 1-sigma uncertainty in the A1 component of the non-gravitational acceleration [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."a2_unc" IS 'Post-fit 1-sigma uncertainty in the A2 component of the non-gravitational acceleration [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."a3_unc" IS 'Post-fit 1-sigma uncertainty in the A3 component of the non-gravitational acceleration [10^(-10) au/d^2]';
COMMENT ON COLUMN "public"."mpc_orbits"."dt_unc" IS 'Post-fit 1-sigma uncertainty in the DeltaT component of the non-gravitational acceleration [days]';
COMMENT ON COLUMN "public"."mpc_orbits"."mean_anomaly_unc" IS 'Post-fit 1-sigma uncertainty in the mean anomaly [degrees] ';
COMMENT ON COLUMN "public"."mpc_orbits"."period_unc" IS 'Post-fit 1-sigma uncertainty in the orbital period [days] ';
COMMENT ON COLUMN "public"."mpc_orbits"."mean_motion_unc" IS 'Post-fit 1-sigma uncertainty in the mean motion [degrees] ';
COMMENT ON COLUMN "public"."mpc_orbits"."epoch_mjd" IS 'Orbit epoch [TT, MJD]';
COMMENT ON COLUMN "public"."mpc_orbits"."h" IS 'Absolute magnitude as computed by OrbFit';
COMMENT ON COLUMN "public"."mpc_orbits"."g" IS 'Slope parameter';
COMMENT ON COLUMN "public"."mpc_orbits"."not_normalized_rms" IS 'Not normalized post-fit RMS [arcseconds]';
COMMENT ON COLUMN "public"."mpc_orbits"."normalized_rms" IS 'Normalized post-fit RMS';
COMMENT ON COLUMN "public"."mpc_orbits"."earth_moid" IS 'Minimum Orbit Intersection Distance [au] with respect to the orbit of the Earth.';
COMMENT ON COLUMN "public"."mpc_orbits"."fitting_datetime" IS 'Date and time recorded when the orbital fit was performed';

-- ----------------------------
-- Table structure for neocp_els
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_els";
CREATE TABLE "public"."neocp_els" (
  "id" int4 NOT NULL,
  "desig" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "els" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "dsc_obs" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "digest2" numeric,
  "flag" char(1) COLLATE "pg_catalog"."default",
  "prep" char(1) COLLATE "pg_catalog"."default",
  "comet" char(1) COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('UTC'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('UTC'::text, now())
)
;
ALTER TABLE "public"."neocp_els" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_els"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_els"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_els"."els" IS 'Orbital element string in the MPC ele220 format. For more information see https://url.usb.m.mimecastprotect.com/s/xuxiCrgWPrT6XV2Y6iNu3T4VAly?domain=minorplanetcenter.net.';
COMMENT ON COLUMN "public"."neocp_els"."dsc_obs" IS '80 or 160-character observation string of the discovery observation.';
COMMENT ON COLUMN "public"."neocp_els"."digest2" IS 'Digest2 score. For more information see https://url.usb.m.mimecastprotect.com/s/ykyVCvm6WyF4oNA54CyC4TQ4WzI?domain=ui.adsabs.harvard.edu and https://url.usb.m.mimecastprotect.com/s/vUUCCwn6XzHPX8ymPIQFjTJslql?domain=ui.adsabs.harvard.edu';
COMMENT ON COLUMN "public"."neocp_els"."flag" IS 'Flag defining if an object is an articial satellite. Flag=S means that the object matched the TLEs of an artificial satellite; Flag=s means that the object did not match any known artificial satellite, but it looks like one (e.g. high geocentric score) ';
COMMENT ON COLUMN "public"."neocp_els"."prep" IS 'Flag=P indicating that the object is being prepared for removal';
COMMENT ON COLUMN "public"."neocp_els"."comet" IS 'Flag=C indicating that the object is a comet. If the flag is present, the object can also be found on the PCCP (https://url.usb.m.mimecastprotect.com/s/VkWACxoWYAIBKMxVBhAH0TyUPkh?domain=minorplanetcenter.net) ';
COMMENT ON COLUMN "public"."neocp_els"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_els"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for neocp_events
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_events";
CREATE TABLE "public"."neocp_events" (
  "id" int4 NOT NULL,
  "desig" text COLLATE "pg_catalog"."default",
  "event_type" text COLLATE "pg_catalog"."default",
  "event_text" text COLLATE "pg_catalog"."default",
  "event_user" text COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('UTC'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('UTC'::text, now())
)
;
ALTER TABLE "public"."neocp_events" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_events"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_events"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_events"."event_type" IS 'Event type, e.g. update, add, remove object';
COMMENT ON COLUMN "public"."neocp_events"."event_text" IS 'A full description of the event type for each object, e.g. Additional obs posted to NEOCP or Object designated K23W00001U (MPEC 2023-W67)';
COMMENT ON COLUMN "public"."neocp_events"."event_user" IS 'User name of who/what processed the event, e.g. process_newneo (automated process), dbell (human)';
COMMENT ON COLUMN "public"."neocp_events"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_events"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for neocp_obs
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_obs";
CREATE TABLE "public"."neocp_obs" (
  "id" int4 NOT NULL,
  "desig" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "trkid" text COLLATE "pg_catalog"."default" NOT NULL,
  "obs80" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "rmstime" numeric,
  "rmsra" numeric,
  "rmsdec" numeric,
  "rmscorr" numeric,
  "force_code" text COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT now(),
  "updated_at" timestamp(6) DEFAULT now()
)
;
ALTER TABLE "public"."neocp_obs" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_obs"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_obs"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_obs"."trkid" IS 'Globally Unique alphnumeric tracklet identifier assigned by MPC';
COMMENT ON COLUMN "public"."neocp_obs"."obs80" IS '80 or 160-Character observation string';
COMMENT ON COLUMN "public"."neocp_obs"."rmstime" IS 'ADES: random uncertainty in time in seconds as estimated by the observer';
COMMENT ON COLUMN "public"."neocp_obs"."rmsra" IS 'ADES: random component of the RA*cos(Dec) uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."neocp_obs"."rmsdec" IS 'ADES: random component of the Dec uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."neocp_obs"."rmscorr" IS 'ADES: correlation between RA and Dec, as estimated by the observer. This is derived from the RA-Dec covariance matrix, where the off-diagonal term is rmsCorr x rmsRA x rmsDec';
COMMENT ON COLUMN "public"."neocp_obs"."force_code" IS 'This column is currently unused. ';
COMMENT ON COLUMN "public"."neocp_obs"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_obs"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for neocp_obs_archive
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_obs_archive";
CREATE TABLE "public"."neocp_obs_archive" (
  "id" int4 NOT NULL,
  "desig" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "trkid" text COLLATE "pg_catalog"."default" NOT NULL,
  "obs80" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "rmstime" numeric,
  "rmsra" numeric,
  "rmsdec" numeric,
  "rmscorr" numeric,
  "force_code" text COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT now(),
  "updated_at" timestamp(6) DEFAULT now()
)
;
ALTER TABLE "public"."neocp_obs_archive" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_obs_archive"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_obs_archive"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_obs_archive"."trkid" IS 'Globally Unique alphnumeric tracklet identifier assigned by MPC';
COMMENT ON COLUMN "public"."neocp_obs_archive"."obs80" IS '80 or 160-Character observation string';
COMMENT ON COLUMN "public"."neocp_obs_archive"."rmstime" IS 'ADES: random uncertainty in time in seconds as estimated by the observer';
COMMENT ON COLUMN "public"."neocp_obs_archive"."rmsra" IS 'ADES: random component of the RA*cos(Dec) uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."neocp_obs_archive"."rmsdec" IS 'ADES: random component of the Dec uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."neocp_obs_archive"."rmscorr" IS 'ADES: correlation between RA and Dec, as estimated by the observer. This is derived from the RA-Dec covariance matrix, where the off-diagonal term is rmsCorr x rmsRA x rmsDec';
COMMENT ON COLUMN "public"."neocp_obs_archive"."force_code" IS 'This column is currently unused. ';
COMMENT ON COLUMN "public"."neocp_obs_archive"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_obs_archive"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for neocp_prev_des
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_prev_des";
CREATE TABLE "public"."neocp_prev_des" (
  "id" int4 NOT NULL,
  "desig" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" text COLLATE "pg_catalog"."default",
  "iau_desig" text COLLATE "pg_catalog"."default",
  "pkd_desig" text COLLATE "pg_catalog"."default",
  "ref" text COLLATE "pg_catalog"."default",
  "digest2" numeric,
  "created_at" timestamp(6) DEFAULT timezone('UTC'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('UTC'::text, now())
)
;
ALTER TABLE "public"."neocp_prev_des" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_prev_des"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_prev_des"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_prev_des"."status" IS 'Reasons for removal (see https://url.usb.m.mimecastprotect.com/s/hOzbCypWZBtJEXLwJUkIPTxbaT6?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."neocp_prev_des"."iau_desig" IS 'Unpacked provisional designation, as specified by the IAU (for more information see https://url.usb.m.mimecastprotect.com/s/gDeTCzqg1Dinvg4ZniJSgT9Jvh6?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."neocp_prev_des"."pkd_desig" IS 'Extended packed provisional designation (for more information see https://url.usb.m.mimecastprotect.com/s/f509CA8EBztVM6EXVUJTBTGF9Vr?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."neocp_prev_des"."ref" IS 'MPEC reference (see https://url.usb.m.mimecastprotect.com/s/T9UBCB1GDATA368rASnU4T2rIiu?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."neocp_prev_des"."digest2" IS 'Digest2 score. For more information see https://url.usb.m.mimecastprotect.com/s/ykyVCvm6WyF4oNA54CyC4TQ4WzI?domain=ui.adsabs.harvard.edu and https://url.usb.m.mimecastprotect.com/s/vUUCCwn6XzHPX8ymPIQFjTJslql?domain=ui.adsabs.harvard.edu';
COMMENT ON COLUMN "public"."neocp_prev_des"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_prev_des"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for neocp_var
-- ----------------------------
--DROP TABLE IF EXISTS "public"."neocp_var";
CREATE TABLE "public"."neocp_var" (
  "id" int4 NOT NULL,
  "desig" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,
  "els" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamp(6) DEFAULT timezone('UTC'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('UTC'::text, now())
)
;
ALTER TABLE "public"."neocp_var" OWNER TO "postgres";
COMMENT ON COLUMN "public"."neocp_var"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."neocp_var"."desig" IS 'Observer-assigned object identifier, unique within a submission batch. It could have been altered by the MPC if linking has been performed between NEOCP objects. ';
COMMENT ON COLUMN "public"."neocp_var"."els" IS 'Orbital element string for each variant orbit in ele220 format. For more information see https://url.usb.m.mimecastprotect.com/s/xuxiCrgWPrT6XV2Y6iNu3T4VAly?domain=minorplanetcenter.net/';
COMMENT ON COLUMN "public"."neocp_var"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."neocp_var"."updated_at" IS 'Date and time of latest row update';

-- ----------------------------
-- Table structure for numbered_identifications
-- ----------------------------
--DROP TABLE IF EXISTS "public"."numbered_identifications";
CREATE TABLE "public"."numbered_identifications" (
  "id" int4 NOT NULL,
  "packed_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "permid" text COLLATE "pg_catalog"."default" NOT NULL,
  "iau_designation" text COLLATE "pg_catalog"."default",
  "iau_name" text COLLATE "pg_catalog"."default",
  "numbered_publication_references" text[] COLLATE "pg_catalog"."default",
  "named_publication_references" text[] COLLATE "pg_catalog"."default",
  "naming_credit" text COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."numbered_identifications" OWNER TO "postgres";
COMMENT ON COLUMN "public"."numbered_identifications"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."numbered_identifications"."packed_primary_provisional_designation" IS 'Packed form of the primary provisional designation (e.g. J81E29H ).';
COMMENT ON COLUMN "public"."numbered_identifications"."unpacked_primary_provisional_designation" IS 'Unpacked form of the primary provisional designation (e.g. 1981 EH29).';
COMMENT ON COLUMN "public"."numbered_identifications"."permid" IS 'Unpacked form of the permanent designation (number without parenthesis, e.g. "500000")';
COMMENT ON COLUMN "public"."numbered_identifications"."iau_designation" IS 'This column is currently unused.';
COMMENT ON COLUMN "public"."numbered_identifications"."iau_name" IS 'This column is currently unused. The MPC is not responsible for naming. ';
COMMENT ON COLUMN "public"."numbered_identifications"."numbered_publication_references" IS 'List of references to any MPC publication(s) including information on the numbering of the corresponding object (e.g. Monthly circulars, etc)';
COMMENT ON COLUMN "public"."numbered_identifications"."named_publication_references" IS 'This column is currently unused. The MPC is not responsible for naming. ';
COMMENT ON COLUMN "public"."numbered_identifications"."naming_credit" IS 'This column is currently unused. The MPC is not responsible for naming. ';
COMMENT ON COLUMN "public"."numbered_identifications"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."numbered_identifications"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."numbered_identifications" IS 'Numbers and Names for any objects that have been Numbered or Named. Linked to primary-provisional-designation in current_identifications';

-- ----------------------------
-- Table structure for obs_alterations_corrections
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obs_alterations_corrections";
CREATE TABLE "public"."obs_alterations_corrections" (
  "id" int4 NOT NULL,
  "obsid_old" text COLLATE "pg_catalog"."default" NOT NULL,
  "obsid_new" text COLLATE "pg_catalog"."default" NOT NULL,
  "publication_ref" text[] COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."obs_alterations_corrections" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obs_alterations_corrections"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."obs_alterations_corrections"."obsid_old" IS 'Unique MPC assigned observation ID (in the obs_sbn table) of the wrong observation that was replaced';
COMMENT ON COLUMN "public"."obs_alterations_corrections"."obsid_new" IS 'Unique MPC assigned observation ID (in the obs_sbn table) of the new corrected observation';
COMMENT ON COLUMN "public"."obs_alterations_corrections"."publication_ref" IS 'Array of references to the publications announcing the correction';
COMMENT ON COLUMN "public"."obs_alterations_corrections"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."obs_alterations_corrections"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."obs_alterations_corrections" IS 'It is intended that the fields in this table will record updates that have been made to the obs table that require subsequent publication to announce UNPUBLISH/UNASSOCIATION/SEND-TO-ITF
Some/all of these changes may be indicated in the obs table itself (e.g. via status flags), but this table is intended to help flag changes to observations that require publication in some form.';

-- ----------------------------
-- Table structure for obs_alterations_deletions
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obs_alterations_deletions";
CREATE TABLE "public"."obs_alterations_deletions" (
  "id" int4 NOT NULL,
  "obsid" text COLLATE "pg_catalog"."default" NOT NULL,
  "publication_ref" text[] COLLATE "pg_catalog"."default",
  "status" int4 NOT NULL,
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."obs_alterations_deletions" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obs_alterations_deletions"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."obs_alterations_deletions"."obsid" IS 'Unique MPC assigned observation ID (in the obs_sbn table) of the deleted observation';
COMMENT ON COLUMN "public"."obs_alterations_deletions"."publication_ref" IS 'Array of references to the publications announcing the deletion';
COMMENT ON COLUMN "public"."obs_alterations_deletions"."status" IS 'Integer describing the publication status: 0=Unpublished (waiting for publication), 1=Published in the DOU, 2=Published in the Monthy Circular';
COMMENT ON COLUMN "public"."obs_alterations_deletions"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."obs_alterations_deletions"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."obs_alterations_deletions" IS 'It is intended that the fields in this table will record updates that have been made to the obs table that require subsequent publication to announce DELETION
Some/all of these changes may be indicated in the obs table itself (e.g. via status flags), but this table is intended to help flag changes to observations that require publication in some form.';

-- ----------------------------
-- Table structure for obs_alterations_redesignations
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obs_alterations_redesignations";
CREATE TABLE "public"."obs_alterations_redesignations" (
  "id" int4 NOT NULL,
  "obsid" text COLLATE "pg_catalog"."default" NOT NULL,
  "packed_provisional_designation_from" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_provisional_designation_from" text COLLATE "pg_catalog"."default" NOT NULL,
  "packed_provisional_designation_to" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_provisional_designation_to" text COLLATE "pg_catalog"."default" NOT NULL,
  "publication_ref" text[] COLLATE "pg_catalog"."default",
  "status" int4 NOT NULL,
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "new_designation_created" bool NOT NULL DEFAULT false
)
;
ALTER TABLE "public"."obs_alterations_redesignations" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."obsid" IS 'Unique MPC assigned observation ID (in the obs_sbn table) of the deleted observation';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."packed_provisional_designation_from" IS 'Previous packed provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/WDsBCDwKGDTMQv3zMf7c2TjfMEy?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."unpacked_provisional_designation_from" IS 'Previous unpacked provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/gDeTCzqg1Dinvg4ZniJSgT9Jvh6?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."packed_provisional_designation_to" IS 'New packed provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/WDsBCDwKGDTMQv3zMf7c2TjfMEy?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."unpacked_provisional_designation_to" IS 'New unpacked provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/gDeTCzqg1Dinvg4ZniJSgT9Jvh6?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."publication_ref" IS 'Array of references to the publications announcing the redesignation';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."status" IS 'Integer describing the publication status: 0=Unpublished (waiting for publication), 1=Published in the DOU, 2=Published in the Monthy Circular';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."updated_at" IS 'Date and time of latest row update';
COMMENT ON COLUMN "public"."obs_alterations_redesignations"."new_designation_created" IS 'Boolean to indicate whether a new designation was created as a result of the redesignations: True=a new designation was created, False=the tracklets were associated to an already existing object';
COMMENT ON TABLE "public"."obs_alterations_redesignations" IS 'It is intended that the fields in this table will record updates that have been made to the obs table that require subsequent publication to announce REDESIGNATIONS
These changes may be indicated in the obs table itself (e.g. via status flags), but this table is intended to help flag changes to observations that require publication in some form.';

-- ----------------------------
-- Table structure for obs_alterations_unassociations
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obs_alterations_unassociations";
CREATE TABLE "public"."obs_alterations_unassociations" (
  "id" int4 NOT NULL,
  "obsid" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_provisional_designation_from" text COLLATE "pg_catalog"."default" NOT NULL,
  "packed_provisional_designation_from" text COLLATE "pg_catalog"."default" NOT NULL,
  "trkmpc_to" text COLLATE "pg_catalog"."default" NOT NULL,
  "publication_ref" text[] COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now())
)
;
ALTER TABLE "public"."obs_alterations_unassociations" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."obsid" IS 'Unique MPC assigned observation ID (in the obs_sbn table) of the deleted observation';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."unpacked_provisional_designation_from" IS 'Previous unpacked provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/gDeTCzqg1Dinvg4ZniJSgT9Jvh6?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."packed_provisional_designation_from" IS 'Previous packed provisional designation (for information on the unpacked provisional designation see https://url.usb.m.mimecastprotect.com/s/WDsBCDwKGDTMQv3zMf7c2TjfMEy?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."trkmpc_to" IS 'New MPC object identifier used to label the observations in the ITF (for information on the ITF, please see https://url.usb.m.mimecastprotect.com/s/gK_uCEKLJEtnK9p2niqfoT7iMn7?domain=minorplanetcenter.net) ';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."publication_ref" IS 'Array of references to the publications announcing the unassociation';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."obs_alterations_unassociations"."updated_at" IS 'Date and time of latest row update';
COMMENT ON TABLE "public"."obs_alterations_unassociations" IS 'It is intended that the fields in this table will record updates that have been made to the obs table that require subsequent publication to announce UNPUBLISH/UNASSOCIATION/SEND-TO-ITF
Some/all of these changes may be indicated in the obs table itself (e.g. via status flags), but this table is intended to help flag changes to observations that require publication in some form.';

-- ----------------------------
-- Table structure for obs_sbn
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obs_sbn";
CREATE TABLE "public"."obs_sbn" (
  "id" int4 NOT NULL,
  "trksub" text COLLATE "pg_catalog"."default",
  "trkid" text COLLATE "pg_catalog"."default",
  "obsid" text COLLATE "pg_catalog"."default",
  "submission_id" text COLLATE "pg_catalog"."default",
  "submission_block_id" text COLLATE "pg_catalog"."default",
  "obs80" text COLLATE "pg_catalog"."default",
  "status" char(1) COLLATE "pg_catalog"."default",
  "ref" text COLLATE "pg_catalog"."default",
  "healpix" int8,
  "permid" text COLLATE "pg_catalog"."default",
  "provid" text COLLATE "pg_catalog"."default",
  "artsat" text COLLATE "pg_catalog"."default",
  "mode" text COLLATE "pg_catalog"."default",
  "stn" text COLLATE "pg_catalog"."default",
  "trx" text COLLATE "pg_catalog"."default",
  "rcv" text COLLATE "pg_catalog"."default",
  "sys" text COLLATE "pg_catalog"."default",
  "ctr" int4,
  "pos1" numeric,
  "pos2" numeric,
  "pos3" numeric,
  "poscov11" numeric,
  "poscov12" numeric,
  "poscov13" numeric,
  "poscov22" numeric,
  "poscov23" numeric,
  "poscov33" numeric,
  "prog" text COLLATE "pg_catalog"."default",
  "obstime" timestamp(6),
  "ra" numeric,
  "dec" numeric,
  "rastar" numeric,
  "decstar" numeric,
  "obscenter" text COLLATE "pg_catalog"."default",
  "deltara" numeric,
  "deltadec" numeric,
  "dist" numeric,
  "pa" numeric,
  "rmsra" numeric,
  "rmsdec" numeric,
  "rmsdist" numeric,
  "rmspa" numeric,
  "rmscorr" numeric,
  "delay" numeric,
  "rmsdelay" numeric,
  "doppler" numeric,
  "rmsdoppler" numeric,
  "astcat" text COLLATE "pg_catalog"."default",
  "mag" numeric,
  "rmsmag" numeric,
  "band" text COLLATE "pg_catalog"."default",
  "photcat" text COLLATE "pg_catalog"."default",
  "photap" numeric,
  "nucmag" int2,
  "logsnr" numeric,
  "seeing" numeric,
  "exp" numeric,
  "rmsfit" numeric,
  "com" int2,
  "frq" numeric,
  "disc" char(1) COLLATE "pg_catalog"."default",
  "subfrm" text COLLATE "pg_catalog"."default",
  "subfmt" text COLLATE "pg_catalog"."default",
  "prectime" int4,
  "precra" numeric,
  "precdec" numeric,
  "unctime" numeric,
  "notes" text COLLATE "pg_catalog"."default",
  "remarks" text COLLATE "pg_catalog"."default",
  "deprecated" char(1) COLLATE "pg_catalog"."default",
  "localuse" text COLLATE "pg_catalog"."default",
  "nstars" int4,
  "prev_desig" text COLLATE "pg_catalog"."default",
  "prev_ref" text COLLATE "pg_catalog"."default",
  "rmstime" numeric,
  "created_at" timestamptz(6) DEFAULT now(),
  "updated_at" timestamptz(6) DEFAULT now(),
  "trkmpc" text COLLATE "pg_catalog"."default",
  "orbit_id" text COLLATE "pg_catalog"."default",
  "designation_asterisk" bool,
  "all_pub_ref" text[] COLLATE "pg_catalog"."default",
  "shapeocc" bool,
  "obssubid" text COLLATE "pg_catalog"."default",
  "replacesobsid" text COLLATE "pg_catalog"."default",
  "group_id" text COLLATE "pg_catalog"."default",
  "vel1" numeric,
  "vel2" numeric,
  "vel3" numeric,
  "fltr" char(3) COLLATE "pg_catalog"."default",
  "obstime_text" text COLLATE "pg_catalog"."default"
)
;
ALTER TABLE "public"."obs_sbn" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obs_sbn"."id" IS 'MPC_ops: PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."obs_sbn"."trksub" IS 'ADES: Observer-assigned object identifier, unique within a submission batch';
COMMENT ON COLUMN "public"."obs_sbn"."trkid" IS 'ADES: Globally unique tracklet identifier assigned by the MPC';
COMMENT ON COLUMN "public"."obs_sbn"."obsid" IS 'ADES: Globally unique observation identifier assigned by the MPC';
COMMENT ON COLUMN "public"."obs_sbn"."submission_id" IS 'MPC_ops: Unique MPC-assigned submission ID';
COMMENT ON COLUMN "public"."obs_sbn"."submission_block_id" IS 'MPC_ops: Unique MPC-assigned submission block ID';
COMMENT ON COLUMN "public"."obs_sbn"."obs80" IS 'MPC_ops: 80 or 160-Character observation string';
COMMENT ON COLUMN "public"."obs_sbn"."status" IS 'MPC_ops: processing status. Allowed values are: P for ufficially published in a circular (DOU, mid-month, monthly), p for accepted and waiting for publication in the next circular, I for ITF observations';
COMMENT ON COLUMN "public"."obs_sbn"."ref" IS 'ADES: Standard reference field used for citations';
COMMENT ON COLUMN "public"."obs_sbn"."healpix" IS 'MPC_ops: A convenience calculation that maps the observed (Ra,Dec) to a healpix (healpix.sourceforge.io) patch of the sky indicated by the recorded integer. The chosen mapping assumes nside = 32768 & nested = True (see https://url.usb.m.mimecastprotect.com/s/ElEwCGwNLJTqoYARqHMhjTBLqnX?domain=astropy-healpix.readthedocs.io), corresponding to a pixel scale of approx 6.4 arcsec.';
COMMENT ON COLUMN "public"."obs_sbn"."permid" IS 'ADES: IAU permanent designation (e.g. the IAU number for a numbered minor planet)';
COMMENT ON COLUMN "public"."obs_sbn"."provid" IS 'ADES: unpacked MPC assigned provisional designation (for more information see https://url.usb.m.mimecastprotect.com/s/hhH_CJEkOMfyPrKvytDiyTyINRa?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."artsat" IS 'ADES: Artificial satellite identifier';
COMMENT ON COLUMN "public"."obs_sbn"."mode" IS 'ADES: mode of instrumentation (for the documentation on valid values, see https://url.usb.m.mimecastprotect.com/s/ANj7CKAlPNf90E4N9S4sLT5dFWq?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."stn" IS 'ADES: Observatory code assigned by the MPC for ground-based or spaced-based stations (for the documentation on valid values, see https://url.usb.m.mimecastprotect.com/s/YAtbCLAmQOfX5jQrXtJt2Tyax9_?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."trx" IS 'ADES: Station codes of transmitting antenna for radar observations';
COMMENT ON COLUMN "public"."obs_sbn"."rcv" IS 'ADES: Station codes of receiving antenna for radar observations';
COMMENT ON COLUMN "public"."obs_sbn"."sys" IS 'ADES: Coordinate frame for roving or space-based station coordinates (for the documentation on valid values, see https://url.usb.m.mimecastprotect.com/s/atXJCM7nRPI9GOz19S2uXT8EBfN?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."ctr" IS 'ADES: Origin of the reference system given by the coordinate frame (sys). Use public SPICE codes for possible values (https://url.usb.m.mimecastprotect.com/s/PPcZCN7oVgI91lj89SEClTydIN1?domain=naif.jpl.nasa.gov), e.g. 399=geocenter';
COMMENT ON COLUMN "public"."obs_sbn"."pos1" IS 'ADES: Position of the observer (see https://url.usb.m.mimecastprotect.com/s/8sU_COJpWjfwoRvjwimFKTGnGub?domain=github.com)';
COMMENT ON COLUMN "public"."obs_sbn"."pos2" IS 'ADES: Position of the observer (see https://url.usb.m.mimecastprotect.com/s/8sU_COJpWjfwoRvjwimFKTGnGub?domain=github.com)';
COMMENT ON COLUMN "public"."obs_sbn"."pos3" IS 'ADES: Position of the observer (see https://url.usb.m.mimecastprotect.com/s/8sU_COJpWjfwoRvjwimFKTGnGub?domain=github.com)';
COMMENT ON COLUMN "public"."obs_sbn"."poscov11" IS 'ADES: Element (1,1) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."poscov12" IS 'ADES: Element (1,2) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."poscov13" IS 'ADES: Element (1,3) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."poscov22" IS 'ADES: Element (2,2) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."poscov23" IS 'ADES: Element (2,3) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."poscov33" IS 'ADES: Element (3,3) of the upper triangular part of the covariance matrix for the observer position in the same units of position coordinates. Missing fields are presumed zero.';
COMMENT ON COLUMN "public"."obs_sbn"."prog" IS 'ADES: Program code assigned by the MPC';
COMMENT ON COLUMN "public"."obs_sbn"."obstime" IS 'ADES: UTC date and time of the observation. ';
COMMENT ON COLUMN "public"."obs_sbn"."ra" IS 'ADES: Right Ascension is decimal degrees in J2000.0 reference frame';
COMMENT ON COLUMN "public"."obs_sbn"."dec" IS 'ADES: Declination is decimal degrees in J2000.0 reference frame';
COMMENT ON COLUMN "public"."obs_sbn"."rastar" IS 'ADES: For occultation, only when stn=244, Right Ascension in the J2000.0 reference frame in decimal degress of the occulted star.';
COMMENT ON COLUMN "public"."obs_sbn"."decstar" IS 'ADES: For occultation, only when stn=244, Declination in the J2000.0 reference frame in decimal degress of the occulted star.';
COMMENT ON COLUMN "public"."obs_sbn"."obscenter" IS 'ADES: Origin of offset observations (full name of a planet or permID or provID for a small body)';
COMMENT ON COLUMN "public"."obs_sbn"."deltara" IS 'ADES: Measured DeltaRA*cos(Dec) in arcsec in the J2000.0 reference frame for offset measurements of a satellite with respect to osbCenter, or for occultation observations with respect to the star (stn=244)';
COMMENT ON COLUMN "public"."obs_sbn"."deltadec" IS 'ADES: Measured DeltaDec in arcsec in the J2000.0 reference frame for offset measurements of a satellite with respect to osbCenter, or for occultation observations with respect to the star (only if stn=244)';
COMMENT ON COLUMN "public"."obs_sbn"."dist" IS 'ADES: Measured distance in arcsec in degrees in the J2000.0 reference frame for offset measurements of a satellite wrt obsCenter, or for occultation observations wrt the star (only if stn=244)';
COMMENT ON COLUMN "public"."obs_sbn"."pa" IS 'ADES: Measured Position Angle in arcsec in degrees in the J2000.0 reference frame for offset measurements of a satellite wrt obsCenter, or for occultation observations wrt the star (only if stn=244)';
COMMENT ON COLUMN "public"."obs_sbn"."rmsra" IS 'ADES: Random component of the RA*cos(Dec) uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."obs_sbn"."rmsdec" IS 'ADES: Random component of the Dec uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."obs_sbn"."rmsdist" IS 'ADES: Random component of the distance uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."obs_sbn"."rmspa" IS 'ADES: Random component of the position angle uncertainty in arcsec as estimated by the observer ';
COMMENT ON COLUMN "public"."obs_sbn"."rmscorr" IS 'ADES: Correlation between RA and Dec or between distance and position angle. This is derived from the covariance matrix, where the off-diagonal term is rmsCorr x rmsRA x rmsDec (for RA and Dec), and rmsCorr x rmsdist x rmspa (for dist and pa)';
COMMENT ON COLUMN "public"."obs_sbn"."delay" IS 'ADES: Observed radar time delay in seconds';
COMMENT ON COLUMN "public"."obs_sbn"."rmsdelay" IS 'ADES: Delay uncertainty in microseconds ';
COMMENT ON COLUMN "public"."obs_sbn"."doppler" IS 'ADES: Observed radar Doppler shift in Hz';
COMMENT ON COLUMN "public"."obs_sbn"."rmsdoppler" IS 'ADES: Doppler shift uncertainty in Hz';
COMMENT ON COLUMN "public"."obs_sbn"."astcat" IS 'ADES: Star catalog used for the astrometric reduction or, in case of occultation observations, for the occulted star (a list of accepted astcat values is availble at the following link https://url.usb.m.mimecastprotect.com/s/Y2UJCP6q0kCZqG3RZfxHmTx-BTZ?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."mag" IS 'ADES: Apparent magnitude in specified band';
COMMENT ON COLUMN "public"."obs_sbn"."rmsmag" IS 'ADES: Apparent magnitude uncertainty in magnitudes';
COMMENT ON COLUMN "public"."obs_sbn"."band" IS 'ADES: Passband designation for photometry (a list of accepted astcat values is availble at the following link https://url.usb.m.mimecastprotect.com/s/BOUpCQArYlf9mAop9S7I6TGrtUv?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."photcat" IS 'ADES: Star catalog used for the photometric reduction (a list of accepted astcat values is availble at the following link https://url.usb.m.mimecastprotect.com/s/Y2UJCP6q0kCZqG3RZfxHmTx-BTZ?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."photap" IS 'ADES: Photometric aperture radius in arcsec';
COMMENT ON COLUMN "public"."obs_sbn"."nucmag" IS 'ADES: Nuclear magnitude flag for comets, primarily used for archival data (photap should be used to communicate information in the new standard). 1=True for archival cometary nuclear magnitude measurements, 0=False otherwise. ';
COMMENT ON COLUMN "public"."obs_sbn"."logsnr" IS 'ADES: The log10 of the signal-to-noise ratio of the source in the image integrated on the entire aperture used for astrometric centroid';
COMMENT ON COLUMN "public"."obs_sbn"."seeing" IS 'ADES: Size of seeing disc in arcsec, measured at Full-Width, Half-Max of the target point spread function';
COMMENT ON COLUMN "public"."obs_sbn"."exp" IS 'ADES: Exposure time in seconds';
COMMENT ON COLUMN "public"."obs_sbn"."rmsfit" IS 'ADES: RMS of fit of astrometric comparison stars in arcsec';
COMMENT ON COLUMN "public"."obs_sbn"."com" IS 'ADES: Flag to indicate that the observation is reduced to the center of mass. Values are 1=True, 0=False. False implies a measurement to the peak power position';
COMMENT ON COLUMN "public"."obs_sbn"."frq" IS 'ADES: Carrier reference frequency in MHz';
COMMENT ON COLUMN "public"."obs_sbn"."disc" IS 'ADES: Discovery flag (more documentation needs to be added here).';
COMMENT ON COLUMN "public"."obs_sbn"."subfrm" IS 'ADES: Originally reported reference frame for angular measurements. The subfrm does not reflect the frame of the associated ADES observations, which are always J2000.0. For example, B1950.0 corresponds to the letter A in column 14 in the 80-column format';
COMMENT ON COLUMN "public"."obs_sbn"."subfmt" IS 'ADES: Format in which the observation was originally submitted to the MPC. This is filled by the MPC (a list of accepted astcat values is availble at the following link https://url.usb.m.mimecastprotect.com/s/g6VaCR8vZmtQ8m51QSZSRT12SFL?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."prectime" IS 'ADES: Precision in millionths of a day of the reported observation time for archival MPC1992 observations and earlier data';
COMMENT ON COLUMN "public"."obs_sbn"."precra" IS 'ADES: Precision for archival MPC1992 observations or earlier data in seconds for RA';
COMMENT ON COLUMN "public"."obs_sbn"."precdec" IS 'ADES: Precision for archival MPC1992 observations or earlier data in arcsec for Dec';
COMMENT ON COLUMN "public"."obs_sbn"."unctime" IS 'ADES: Estimated systematic time error in seconds. This field indicates a presumed level of systematic clock error. ';
COMMENT ON COLUMN "public"."obs_sbn"."notes" IS 'ADES: A set of one-character note flags to communicate observing circumstances (a list of accepted notes values is availble at the following link https://url.usb.m.mimecastprotect.com/s/h97XCVJz4qfX1wg6XtZTATE77JB?domain=minorplanetcenter.net';
COMMENT ON COLUMN "public"."obs_sbn"."remarks" IS 'ADES: A comment provided by the observer. ';
COMMENT ON COLUMN "public"."obs_sbn"."deprecated" IS 'ADES: Deprecated observation that is preserved for historical purpose. Do not use it in the orbit fitting. The only allowed value is X';
COMMENT ON COLUMN "public"."obs_sbn"."localuse" IS 'ADES: Container to hold subelements carrying ancillary information not envisioned by the standard';
COMMENT ON COLUMN "public"."obs_sbn"."nstars" IS 'ADES: Number of stars in the astrometric fit';
COMMENT ON COLUMN "public"."obs_sbn"."prev_desig" IS 'MPC_ops: Previous designation for a redesignated observations (see also the obs_alteration_redesignations table https://url.usb.m.mimecastprotect.com/s/p4WHCWWA5rTxv9DKxURUQTo9Psq?domain=minorplanetcenter.net)';
COMMENT ON COLUMN "public"."obs_sbn"."prev_ref" IS 'MPC_ops: Previous publication references';
COMMENT ON COLUMN "public"."obs_sbn"."rmstime" IS 'ADES: Random uncertainty in time as estimated by the observer';
COMMENT ON COLUMN "public"."obs_sbn"."created_at" IS 'MPC_ops: Date and time of initial row insert';
COMMENT ON COLUMN "public"."obs_sbn"."updated_at" IS 'MPC_ops: Date and time of latest row update';
COMMENT ON COLUMN "public"."obs_sbn"."trkmpc" IS 'ADES: MPC-internal object identifier';
COMMENT ON COLUMN "public"."obs_sbn"."orbit_id" IS 'MPC_ops: Unique identifier for the orbit calculation. This field is not currently used';
COMMENT ON COLUMN "public"."obs_sbn"."designation_asterisk" IS 'MPC_ops: Equivalent of the asterisks used to mark initial tracklets for component provisional designations. One object can have multiple discovery_asterisks';
COMMENT ON COLUMN "public"."obs_sbn"."all_pub_ref" IS 'MPC_ops: Array of publication references that contained any information about the observation';
COMMENT ON COLUMN "public"."obs_sbn"."shapeocc" IS 'ADES: For occultation observations, a flag to indicate that the observation reduction assumes a shape-based plane-of-sky cross-section. Values are 1=True or 0=False that implies that a circular cross section was assumed';
COMMENT ON COLUMN "public"."obs_sbn"."obssubid" IS 'ADES: Observation identifier, optionally included by the observer in the submission, that is unique to a given observing program';
COMMENT ON COLUMN "public"."obs_sbn"."replacesobsid" IS 'MPC_ops: Observation identifier of the old published observations that has been replaced by this new observation. This field is not currently used. ';
COMMENT ON COLUMN "public"."obs_sbn"."group_id" IS 'MPC_ops: Observation group identifier used to group duplicate/near-duplicate observations. This field is not currently used';

-- ----------------------------
-- Table structure for obscodes
-- ----------------------------
--DROP TABLE IF EXISTS "public"."obscodes";
CREATE TABLE "public"."obscodes" (
  "id" int4 NOT NULL,
  "obscode" varchar(4) COLLATE "pg_catalog"."default",
  "longitude" numeric,
  "rhocosphi" numeric,
  "rhosinphi" numeric,
  "name" varchar COLLATE "pg_catalog"."default",
  "firstdate" varchar(10) COLLATE "pg_catalog"."default",
  "lastdate" varchar(10) COLLATE "pg_catalog"."default",
  "web_link" text COLLATE "pg_catalog"."default",
  "created_at" timestamp(6) DEFAULT now(),
  "updated_at" timestamp(6) DEFAULT now(),
  "short_name" varchar(255) COLLATE "pg_catalog"."default",
  "uses_two_line_observations" bool,
  "old_names" varchar[] COLLATE "pg_catalog"."default",
  "name_utf8" varchar(255) COLLATE "pg_catalog"."default",
  "name_latex" varchar(255) COLLATE "pg_catalog"."default",
  "observations_type" varchar(255) COLLATE "pg_catalog"."default"
)
;
ALTER TABLE "public"."obscodes" OWNER TO "postgres";
COMMENT ON COLUMN "public"."obscodes"."obscode" IS 'Obscode station code';
COMMENT ON COLUMN "public"."obscodes"."longitude" IS 'Longitude of the station code (in degrees east of Greenwich)';
COMMENT ON COLUMN "public"."obscodes"."rhocosphi" IS 'Parallax constants where phi is the geocentric latitude and rho is the geocentric distance in earth radii';
COMMENT ON COLUMN "public"."obscodes"."rhosinphi" IS 'Parallax constants where phi is the geocentric latitude and rho is the geocentric distance in earth radii';
COMMENT ON COLUMN "public"."obscodes"."name" IS 'Name of the stations code ';
COMMENT ON COLUMN "public"."obscodes"."firstdate" IS 'Start date for the observatory code';
COMMENT ON COLUMN "public"."obscodes"."lastdate" IS 'Last date for the observatory code';
COMMENT ON COLUMN "public"."obscodes"."web_link" IS 'Link for the station webpage';
COMMENT ON COLUMN "public"."obscodes"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."obscodes"."updated_at" IS 'Date and time of latest row update';
COMMENT ON COLUMN "public"."obscodes"."short_name" IS 'Short name used for MPC publications and files';
COMMENT ON COLUMN "public"."obscodes"."uses_two_line_observations" IS 'Boolean indicating whether the station code needs a second line when the position is reported in the MPC-1992 80-column format (e.g. satellite observations)';
COMMENT ON COLUMN "public"."obscodes"."old_names" IS 'Old names for the observatory';
COMMENT ON COLUMN "public"."obscodes"."name_utf8" IS 'Name of the observatory code in UTF-8 format';
COMMENT ON COLUMN "public"."obscodes"."name_latex" IS 'Name of the observatory code in latex format';
COMMENT ON COLUMN "public"."obscodes"."observations_type" IS 'Observation type (e.g. optical, radar, satellite, occultation)';

-- ----------------------------
-- Table structure for primary_objects
-- ----------------------------
--DROP TABLE IF EXISTS "public"."primary_objects";
CREATE TABLE "public"."primary_objects" (
  "id" int4 NOT NULL,
  "packed_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "unpacked_primary_provisional_designation" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" int4,
  "standard_minor_planet" bool NOT NULL DEFAULT false,
  "standard_epoch" bool NOT NULL DEFAULT false,
  "orbfit_epoch" bool NOT NULL DEFAULT false,
  "nongravs" bool NOT NULL DEFAULT false,
  "satellite" bool NOT NULL DEFAULT false,
  "comet" bool NOT NULL DEFAULT false,
  "barycentric" bool NOT NULL DEFAULT false,
  "no_orbit" bool NOT NULL DEFAULT true,
  "orbit_publication_references" text[] COLLATE "pg_catalog"."default",
  "flag_all_object_obs_consistent" bool NOT NULL DEFAULT false,
  "flag_orbit_calculated_from_consistent_obs" bool NOT NULL DEFAULT false,
  "flag_allowed_external" bool NOT NULL DEFAULT false,
  "created_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "updated_at" timestamp(6) DEFAULT timezone('utc'::text, now()),
  "orbit_published" int4,
  "object_type" int4
)
;
ALTER TABLE "public"."primary_objects" OWNER TO "postgres";
COMMENT ON COLUMN "public"."primary_objects"."id" IS 'PostgreSQL automatically generated identifier';
COMMENT ON COLUMN "public"."primary_objects"."packed_primary_provisional_designation" IS 'Packed form of the primary provisional designation (e.g. K17P08M)';
COMMENT ON COLUMN "public"."primary_objects"."unpacked_primary_provisional_designation" IS 'Unpacked form of the primary provisional designation (e.g. 2017 PM8)';
COMMENT ON COLUMN "public"."primary_objects"."status" IS 'Result of the orbit fitting. This is still not used';
COMMENT ON COLUMN "public"."primary_objects"."standard_minor_planet" IS 'Boolean to indicate whether the orbit of the object is specified in the standard_minor_planet table. This is not used right now, but we might use it in the future';
COMMENT ON COLUMN "public"."primary_objects"."standard_epoch" IS 'If the object is in the standard_minor_planet table, this boolean indicates whether an orbit at the standard-epoch is populated';
COMMENT ON COLUMN "public"."primary_objects"."orbfit_epoch" IS 'If the object is in the standard_minor_planet table, this boolean indicates whether the orbit at the mid-observation epoch is populated';
COMMENT ON COLUMN "public"."primary_objects"."nongravs" IS 'Boolean to indicate whether the orbit of the object is specified in the table containing orbits with nongravitational perturbations. At the moment this is not used because we do not have a table for the orbits computed including nongravitational perturbations, even though we compute them. We might use this flag in the future it to indicate wheter we computed the orbit of the object using non-gravitational perturbations. ';
COMMENT ON COLUMN "public"."primary_objects"."satellite" IS 'Boolean to indicate whether the object-orbit is specified in the satellite table';
COMMENT ON COLUMN "public"."primary_objects"."comet" IS 'Boolean to indicate whether the object-orbit is specified in the comet table. The values are currently false because we are not saving comet orbits in a comet table';
COMMENT ON COLUMN "public"."primary_objects"."barycentric" IS 'Boolean to indicate whether the orbit for the object is in a barycentric table. The values for this field are always false because we are not computing barycentric orbits.';
COMMENT ON COLUMN "public"."primary_objects"."no_orbit" IS 'Flag to indicate those cases for which it was not possible to compute an orbit.';
COMMENT ON COLUMN "public"."primary_objects"."orbit_publication_references" IS 'Array of references to MPC publication(s) containing this particular orbit calculation (e.g. DOU MPEC, mid-month, Monthly-MPC, etc)';
COMMENT ON COLUMN "public"."primary_objects"."flag_all_object_obs_consistent" IS 'Flag to indicate if all observations for an object have been checked to be consistent with obs files. We are not currently using this field. ';
COMMENT ON COLUMN "public"."primary_objects"."flag_orbit_calculated_from_consistent_obs" IS 'Flag to indicate if the the orbit was calculated using the observations flagged as consistent. This flag is not used';
COMMENT ON COLUMN "public"."primary_objects"."flag_allowed_external" IS 'Flag to indicate if the orbit has been computed using all the observations available and if the observations were consisten with the flat files. This flat is not used.';
COMMENT ON COLUMN "public"."primary_objects"."created_at" IS 'Date and time of initial row insert';
COMMENT ON COLUMN "public"."primary_objects"."updated_at" IS 'Date and time of latest row update';
COMMENT ON COLUMN "public"."primary_objects"."orbit_published" IS 'Flag indicating if the orbit has been published in a Circular. Field values are: 0=unpublished ; 1=published as MPEC; 2=published in DOU ; 3=published in mid-month ; 4=published in monthly. Please note that we are talking about orbit publication and not object designations';
COMMENT ON COLUMN "public"."primary_objects"."object_type" IS 'Integer to indicate the object type as defined in: https://url.usb.m.mimecastprotect.com/s/9FytCnGWL0cxQOm2xUJhpTJmToG?domain=minorplanetcenter.net/';
COMMENT ON TABLE "public"."primary_objects" IS 'All Objects Live Here: Labelled by their primary provisional designation. Fields indicate the tables in which any orbit information might be found';

-- ----------------------------
-- Indexes structure for table comet_names
-- ----------------------------
CREATE INDEX "comet_names_packed_primary_provisional_designation_idx" ON "public"."comet_names" USING btree (
  "packed_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table comet_names
-- ----------------------------
ALTER TABLE "public"."comet_names" ADD CONSTRAINT "comet_names_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table current_identifications
-- ----------------------------
CREATE INDEX "current_identifications_packed_primary_provisional_designation_" ON "public"."current_identifications" USING btree (
  "packed_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "current_identifications_packed_secondary_provisional_designatio" ON "public"."current_identifications" USING btree (
  "packed_secondary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "current_identifications_updated_at" ON "public"."current_identifications" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table current_identifications
-- ----------------------------
ALTER TABLE "public"."current_identifications" ADD CONSTRAINT "current_identifications_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table minor_planet_names
-- ----------------------------
ALTER TABLE "public"."minor_planet_names" ADD CONSTRAINT "minor_planet_names_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table mpc_orbits
-- ----------------------------
CREATE INDEX "mpc_orbits_updated_at_idx" ON "public"."mpc_orbits" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "packed_primary_provisional_idx" ON "public"."mpc_orbits" USING btree (
  "packed_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "unpacked_primary_provisional_idx" ON "public"."mpc_orbits" USING btree (
  "unpacked_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table mpc_orbits
-- ----------------------------
ALTER TABLE "public"."mpc_orbits" ADD CONSTRAINT "mpc_orbits_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_els
-- ----------------------------
CREATE INDEX "neocp_els_created_at_key" ON "public"."neocp_els" USING btree (
  "created_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_els_digest2_key" ON "public"."neocp_els" USING btree (
  "digest2" "pg_catalog"."numeric_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table neocp_els
-- ----------------------------
ALTER TABLE "public"."neocp_els" ADD CONSTRAINT "neocp_els_desig_key" UNIQUE ("desig");

-- ----------------------------
-- Primary Key structure for table neocp_els
-- ----------------------------
ALTER TABLE "public"."neocp_els" ADD CONSTRAINT "neocp_els_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_events
-- ----------------------------
CREATE INDEX "neocp_events_desig_key" ON "public"."neocp_events" USING btree (
  "desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_events_event_text_key" ON "public"."neocp_events" USING btree (
  "event_text" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_events_event_type_key" ON "public"."neocp_events" USING btree (
  "event_type" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_events_event_user_key" ON "public"."neocp_events" USING btree (
  "event_user" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_events_updated_at_idx" ON "public"."neocp_events" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table neocp_events
-- ----------------------------
ALTER TABLE "public"."neocp_events" ADD CONSTRAINT "neocp_events_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_obs
-- ----------------------------
CREATE INDEX "neocp_obs_created_at_key" ON "public"."neocp_obs" USING btree (
  "created_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_desig_key" ON "public"."neocp_obs" USING btree (
  "desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_substring_idx" ON "public"."neocp_obs" USING btree (
  "substring"(obs80::text, 16, 17) COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_trkid_key" ON "public"."neocp_obs" USING btree (
  "trkid" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_updated_at_key" ON "public"."neocp_obs" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table neocp_obs
-- ----------------------------
ALTER TABLE "public"."neocp_obs" ADD CONSTRAINT "neocp_obs_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_obs_archive
-- ----------------------------
CREATE INDEX "neocp_obs_archive_created_at_key" ON "public"."neocp_obs_archive" USING btree (
  "created_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_archive_desig_key" ON "public"."neocp_obs_archive" USING btree (
  "desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_archive_trkid_key" ON "public"."neocp_obs_archive" USING btree (
  "trkid" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_obs_archive_updated_at_key" ON "public"."neocp_obs_archive" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table neocp_obs_archive
-- ----------------------------
ALTER TABLE "public"."neocp_obs_archive" ADD CONSTRAINT "neocp_obs_archive_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_prev_des
-- ----------------------------
CREATE INDEX "neocp_prev_des_created_at_key" ON "public"."neocp_prev_des" USING btree (
  "created_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_desig_key" ON "public"."neocp_prev_des" USING btree (
  "desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_iau_desig_key" ON "public"."neocp_prev_des" USING btree (
  "iau_desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_pkd_desig_key" ON "public"."neocp_prev_des" USING btree (
  "pkd_desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_ref_key" ON "public"."neocp_prev_des" USING btree (
  "ref" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_status_key" ON "public"."neocp_prev_des" USING btree (
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_prev_des_updated_at_idx" ON "public"."neocp_prev_des" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table neocp_prev_des
-- ----------------------------
ALTER TABLE "public"."neocp_prev_des" ADD CONSTRAINT "neocp_prev_des_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table neocp_var
-- ----------------------------
CREATE INDEX "neocp_var_created_at_key" ON "public"."neocp_var" USING btree (
  "created_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_var_desig_key" ON "public"."neocp_var" USING btree (
  "desig" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "neocp_var_updated_at_idx" ON "public"."neocp_var" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table neocp_var
-- ----------------------------
ALTER TABLE "public"."neocp_var" ADD CONSTRAINT "neocp_var_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table numbered_identifications
-- ----------------------------
CREATE UNIQUE INDEX "numbered_identifications_iau_name_idx" ON "public"."numbered_identifications" USING btree (
  "iau_name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "numbered_identifications_packed_primary_provisional_designation" ON "public"."numbered_identifications" USING btree (
  "packed_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "numbered_identifications_permid_idx" ON "public"."numbered_identifications" USING btree (
  "permid" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "numbered_identifications_unpacked_primary_provisional_designati" ON "public"."numbered_identifications" USING btree (
  "unpacked_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "numbered_identifications_updated_at_idx" ON "public"."numbered_identifications" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table numbered_identifications
-- ----------------------------
ALTER TABLE "public"."numbered_identifications" ADD CONSTRAINT "numbered_identifications_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table obs_alterations_corrections
-- ----------------------------
ALTER TABLE "public"."obs_alterations_corrections" ADD CONSTRAINT "obs_alterations_corrections_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table obs_alterations_deletions
-- ----------------------------
CREATE INDEX "obs_alterations_deletions_updated_at_idx" ON "public"."obs_alterations_deletions" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table obs_alterations_deletions
-- ----------------------------
ALTER TABLE "public"."obs_alterations_deletions" ADD CONSTRAINT "obs_alterations_deletions_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table obs_alterations_redesignations
-- ----------------------------
ALTER TABLE "public"."obs_alterations_redesignations" ADD CONSTRAINT "obs_alterations_redesignations_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table obs_alterations_unassociations
-- ----------------------------
ALTER TABLE "public"."obs_alterations_unassociations" ADD CONSTRAINT "obs_alterations_unassociations_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table obs_sbn
-- ----------------------------
CREATE INDEX "obs_sbn_count_simple_idx" ON "public"."obs_sbn" USING btree (
  (1) "pg_catalog"."int4_ops" ASC NULLS LAST
);
CREATE INDEX "obs_sbn_obstime_idx" ON "public"."obs_sbn" USING btree (
  "obstime" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);
CREATE INDEX "obs_sbn_obstime_text_idx" ON "public"."obs_sbn" USING btree (
  "obstime_text" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "obs_sbn_stn_idx" ON "public"."obs_sbn" USING btree (
  "stn" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "obs_sbn_submission_block_id_idx" ON "public"."obs_sbn" USING btree (
  "submission_block_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "obs_sbn_updated_at_idx" ON "public"."obs_sbn" USING btree (
  "updated_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table obs_sbn
-- ----------------------------
ALTER TABLE "public"."obs_sbn" ADD CONSTRAINT "obs_sbn_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table obscodes
-- ----------------------------
CREATE INDEX "obscodes_name_idx" ON "public"."obscodes" USING btree (
  "name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table obscodes
-- ----------------------------
ALTER TABLE "public"."obscodes" ADD CONSTRAINT "obscodes_obscode_key" UNIQUE ("obscode");

-- ----------------------------
-- Primary Key structure for table obscodes
-- ----------------------------
ALTER TABLE "public"."obscodes" ADD CONSTRAINT "obscodes_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table primary_objects
-- ----------------------------
CREATE UNIQUE INDEX "primary_objects_packed_primary_provisional_designation_idx" ON "public"."primary_objects" USING btree (
  "packed_primary_provisional_designation" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "primary_objects_updated_at_idx" ON "public"."primary_objects" USING btree (
  "updated_at" "pg_catalog"."timestamp_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table primary_objects
-- ----------------------------
ALTER TABLE "public"."primary_objects" ADD CONSTRAINT "primary_objects_packed_primary_provisional_designation_key" UNIQUE ("packed_primary_provisional_designation");
ALTER TABLE "public"."primary_objects" ADD CONSTRAINT "primary_objects_unpacked_primary_provisional_designation_key" UNIQUE ("unpacked_primary_provisional_designation");

-- ----------------------------
-- Checks structure for table primary_objects
-- ----------------------------
ALTER TABLE "public"."primary_objects" ADD CONSTRAINT "otc" CHECK (standard_minor_planet = true AND nongravs = false AND satellite = false AND comet = false AND no_orbit = false OR standard_minor_planet = false AND nongravs = true AND satellite = false AND comet = false AND no_orbit = false OR standard_minor_planet = false AND nongravs = false AND satellite = true AND comet = false AND no_orbit = false OR standard_minor_planet = false AND nongravs = false AND satellite = false AND comet = true AND no_orbit = false OR standard_minor_planet = false AND nongravs = false AND satellite = false AND comet = false AND no_orbit = true);

-- ----------------------------
-- Primary Key structure for table primary_objects
-- ----------------------------
ALTER TABLE "public"."primary_objects" ADD CONSTRAINT "primary_objects_pkey" PRIMARY KEY ("id");

