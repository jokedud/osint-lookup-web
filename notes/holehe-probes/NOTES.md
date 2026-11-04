# Holehe 1.61 audit (2026-11-04, run from a US residential-like IP, not Render)

Baseline (`baseline.py`): test@gmail.com -> 17 found / 71 couldn't check / 34 not found (122 modules);
john.smith@gmail.com -> 13 / 68 / 41. `diag.py` runs each module and prints exceptions.
Negative control used: zq5b723a25ee53@gmail.com.

## Working public signals (verified: registered vs unregistered differ)
| Site | Request | Registered | Not registered |
|---|---|---|---|
| Firefox | POST api.accounts.firefox.com/v1/account/status {"email"} | {"exists":true} | {"exists":false} |
| Spotify | GET spclient.wg.spotify.com/signup/public/v1/account?validate=1&email= | status 20 | status 1 (130 = invalid email) |
| Microsoft | GET odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress= | MSAccount | Neither |
| Adobe | POST auth.services.adobe.com/signin/v2/users/accounts {"username"} + X-IMS-ClientId: adobedotcom2 | non-empty list | [] |
| Atlassian | POST id.atlassian.com/rest/check-username {"username"} | action no_action (+social) | action signup |
| HubSpot | POST api.hubspot.com/login-api/v1/login {email,password:dummy} | status != INVALID_USER (e.g. PASSWORD_DEPRECATED) | INVALID_USER |
| Patreon | POST patreon.com/api/auth?include=user.null&fields[user]=[]&json-api-version=1.0 (vnd.api+json, patreon_auth.email, allow_account_creation false) | next_auth_step password | signup |
| Tumblr | GET /register -> "API_TOKEN"; POST /api/v2/register/account/validate Bearer token {email,tumblelog,password} | 400 "User already exists" | 200 |
| Codecademy | GET /register -> meta csrf-token; POST /register/validate {"user":{"email"}} X-CSRF-Token | 400 "has already been taken" | 200 {} |
| Vivino | POST vivino.com/api/login {email,password:"e"} | other error (e.g. "account has been locked") | "The supplied email does not exist" |
| Bitmoji/Snapchat | POST bitmoji.api.snapchat.com/api/user/find form email | 200 {"account_type":...} | 204 |
| WordPress.com | GET public-api.wordpress.com/rest/v1.1/users/{email}/auth-options | 403 email_login_not_allowed (or 200) | 404 unknown_user |
| Zoho | GET accounts.zoho.com/signin (iamcsr cookie); POST /signin/v2/lookup/{email} X-ZCSRF-TOKEN: iamcsrcoo=<cookie> | "lookup" object | U401 User does not exists |
| Komoot | POST komoot.com/v1/signin {"email","reason":"header"} | type login | type register |
| Chess.com (new) | GET chess.com/callback/email/available?email= | isEmailAvailable false | true |
| Duolingo | GET duolingo.com/2017-06-30/users?email= | users non-empty | [] |
| Holehe modules still fine | lastpass, twitter, plurk, anydo, flickr, replit, freelancer, devrant, eventbrite, rambler, diigo, teamtreehouse, onlinesequencer, office365, insightly, xvideos, xnxx | | |

## Blocked / no working signal found
- Bot wall (403/Cloudflare/DataDome): github (signup page 403), soundcloud, codepen, smule, ebay, strava, vsco, gitlab, picsart, grammarly (custom check, 403), pinterest (old and EmailExistsResource 403/404).
- Instagram 429 after csrf; Discord hCaptcha; Imgur 412 "security check"; Yahoo login page has no acrumb form for plain HTTP.
- Endpoint gone: rocketreach validateEmail 404, issuu 503, docker check-email 404, evernote Login.action has no hpts, buymeacoffee no bmc_csrf_token.
- Not discriminating: last.fm partial/validate (said valid for test@gmail.com), wattpad users/validate (OK for both), gravatar (works, but test@ has no profile).
- Not probed: nike, garmin, samsung, quora, xing, myspace (401), amazon, archive, mail_ru (gmail invalid), protonmail (proton addrs only), deliveroo (DNS fail), venmo (timeout), and the small forums.
