import sys,unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root),str(root/'tests')]
names=['test_wallet_server19','test_build18','test_build34','test_build39','test_build40','test_wallet_server2.Relay','test_wallet_server11','test_wallet_server10','test_wallet_server15.FirstIdentity','test_build12','test_build33.PublicIdentityCache','test_build54.Responsiveness.test_identity_reply_is_accepted_without_running_routine_sync_reconciliation','test_build65']
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names));sys.exit(not r.wasSuccessful())
