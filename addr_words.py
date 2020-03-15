byte_words = '''
able ably ache achy acid acme acne acre acts adam adar aeon aero aery afar aged
ahem ahoy aide aint airy ajar akin alan alas alba alco alec alef alex alfa ally
alma aloe also alto alum amar amen amid amir ammo amok amos anal anat andy anew
anna anne anon anti anus apex aqua area arms army arse atom atop aunt aura auto
avid away awry axis babe baby bach back bait bald balm bane bang bank bark barn
bash bask bath bead beak beam bean beat beef been beer bees bell belt best beth
bias bike bill bind bird bite blip blob bloc blue blur boat body bola bolt bomb
bond bone bong boom boot boss brag brat brim bull bump burp busk bust busy butt
buzz cage cake calf calm cape card cart case cash cave cell chat chef chew chia
chin chip chug city clam clan clap claw clay clip club clue coal coat coca code
coin cold cone cook cool cord cork corn cost cosy crab crap crib cuba cube cult
curb cure cusp cute cyan dali dare dash data date dawn dead deaf deal dean dear
debt deck deed deer defy demi desk dial dibs dice dire dirt diva dive dock does
doom door dorm dose doug dove drag draw dual duck dude duel duet dull dumb dump
dune dunk dusk dust duty each ease east easy eats echo edge else envy epic even
ever evil exam exit face fact fade fail fame farm fast fate fear feel fiat film
'''.split()

def address_to_words(ip, port):
    nums = [int(x) for x in ip.split('.')] + [port % 256, port // 256]
    return ' '.join(byte_words[x] for x in nums)

def words_to_address(words):
    parts = words.split()
    if len(parts) != 6:
        return None
    try:
        nums = [byte_words.index(x) for x in parts]
    except ValueError:
        return None
    return '.'.join(str(x) for x in nums[:4]), nums[4] + 256*nums[5]
