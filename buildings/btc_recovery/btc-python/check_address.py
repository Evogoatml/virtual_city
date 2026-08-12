#!/usr/bin/env python3
"""
Bitcoin xprv Matcher - All xprv keys found
"""

USER_ADDRESSES = [
    "18qZ6nkZAQNCVktMixd9Kb3YJ5KPx4E5ov",
    "14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC",
]

XPRV_KEYS = [
    (
        "xprv9ypTTzMuqDr78NRavpPGjkmwC11BimwGop46HKJohqc8XSBDiTwWwc8EgzF3b1Njfnqxtb3RFJ2WEK4Uf5XL3hnKitu1YJghiDDYuwEGrTz",
        "wallets/seed",
    ),
    (
        "xprv9yMEmdggNa2UqkAnhD1H5bUUV8dUA21CgrAtzSwYB2gFCh5pz817RoZf7o7f164ZXAQwyH1kuBptKP4LFLRYpwPV2TCNL3trBPc7XuoLUpM",
        "wallets/seed1",
    ),
    (
        "xprv9zAwPRjY6GNaQq3Q9sqSvaKE8QQmLNfmQ6cft88sVsm1UZtN76sm1u3HoiiQbxYFN4JvAdZrFcNjBv8eVj7D57YD6Z4pDb1aTT9oV2WAZty",
        "wallets/seed3",
    ),
    (
        "xprv9zAndnZMJQZpfi8RQDpQtgNuuhWRSh4WofMAp5GPs54mDrggS9Pbnq4iRUz8SQrFqpv7eFetkx1WPCTAh9Z9BfP9neSpVF3t83ain68QLaF",
        "wallets/seed4",
    ),
    (
        "xprv9y3Mvw1tyGPNshmo6VwRFMQxHGGXLC5KrAZbLsnjUzSrDa2utZSBbe7RfU7ox8kn56bivs6ZrC9cDYUxiPy8DZYXDpqsGeLNzXDvJcJZUC5",
        "SEEDS/BIP39",
    ),
    (
        "xprv9s21ZrQH143K3vfqWsGCy3QiqG1NLiGBisMNsXzV8HaebECaBvHiWVozaSefjQwwNvji13vg3bn6pF2gQ2xYW7JmnjpBkYL3Lru6TdBRyKJ",
        "SEEDS/BIP39 Root",
    ),
    (
        "xprv9y4nb6akxru8r68sygrihutfqugmnxmif83vitf65mobjrrryhwc1m8mszjsmz1nqcjntxmf99skgkkcqqgziecvdkwa4kqxsh5srnazrin",
        "01_SEEDS/seed",
    ),
    (
        "xprv9yujnqzsx3qdwmesx4rpvkdckhlrksqmrgkmpdyrxwj4cckrtpj7qgbzlbjqrmgy7dhxtcpqfcesuakjpuhrs8bg5bsintuszo32zsgi5tn",
        "01_SEEDS/seed2",
    ),
    (
        "xprv9xykdzcqo2ahywcogwpyc2zyrascky9agyexy5gpjbtwdqexg35z2ujgmt8bynmske1mtvd3qdl33zj8af3tsrbtltmjtxr44dkxftn65qv",
        "01_SEEDS/seed3",
    ),
    (
        "xprv9s21ZrQH143K3TnoUsxXKLF43XDesqjXYj1GLxsmJtNtTcBPLriFFNEFknAqC8HmKipgFNDxb2P2Z3DPiW7YsPy1HJ4TUQ6qi4vzJSVVhSf",
        "01_SEEDS/seed4",
    ),
    (
        "xprv9s21ZrQH143K3C7E7q7TsRFmB1yNqtQQrgN1uFCtwQEEQAskkJ551iSnGSuLryCCusJXPXoCduRm4A5nN77NC5b4qSgVYUd9f1WE1gejFeH",
        "01_SEEDS/seed5",
    ),
    (
        "xprv9a41z7zogvvwxvsgdkuhdy1skmdb533pjdz7j6n6mv6us3ze1ai8fha8kmhscgpwmj4wgglyqjgpie1rfsruouihuzrepsl39unde3bbdu76",
        "01_SEEDS/seed6",
    ),
    (
        "xprv9s21ZrQH143K43UEbLGTvVhvZvt3LreGQuDHAJybLczzwUjFfXz32q5H3XEzUGSfnnUX1yYWd6efjKef9Xo6VEHGpnqujPEo4mSnT19tmYD",
        "01_SEEDS/New Text Doc 4",
    ),
    (
        "xprv9s21ZrQH143K4SKNRGhMQuSE6vmPoeFyHcdRBSZUvCNGYpX5aNCRjNQTyPzdYRcS61ftSbsDSi9ZqpWjoreQ5CTUqP64GpuTFY4gBV68VZo",
        "01_SEEDS/New Text Doc 2",
    ),
    (
        "xprv9s21ZrQH143K24RyHcDXFhy93W2VPwRf1VC4jc5y2fJHJHVcqdDNTxLTgLxkLnQmfPjnXs31cLmHchzKduATvuFkQXBrnLSmg7QTiGoTK4d",
        "01_SEEDS/New Text Doc 2b",
    ),
    (
        "xprv9s21ZrQH143K3YhAX1KJLvnrHgABsvXqJknfzWXtJkmuT5t9oDRzvmwdqQhUgx5V1ftnRWuMWjKokPuEGb3Vh7FUAwMPptD6nnropFztN5V",
        "01_SEEDS/New Text Doc 2c",
    ),
    (
        "xprv9s21ZrQH143K3Rq11UKkQJq6EDsFsZp1NAeEjeWe4r9s3yyYaeuvfJS1aGKLzq3dCCHYutuS6FDXmGgihrVh3UBcuUGLNVVjZEU4UR8gDFn",
        "01_SEEDS/New Text Doc 2d",
    ),
    (
        "zprvAZeZXCaJb4KgY574yZRjjTcdBWsfbzBnuH9fpcB2ZRWkcSq4Y7EsgnoD8RghnQevaj9GL5rAcRAGojGQbowKNSkjy2Xu49P4kKbCnnkr6J7",
        "wallets/boss",
    ),
    (
        "zprvAZdo78hALyqzvSkat2Y13zQdGeJMhjnWFiEWcvqisd3ZTiaiW1v6U8JKqyaLa7JMbZmwtLSv31cGXB5wHMzexs5mU2JMuJqYfRKw2zVUrLb",
        "wallets/goat",
    ),
    (
        "zprvAZDx7CDUJyRcjaJo76KpvQji1KhfYCYWeEaKZx5dV2wt3ibbqe8JNXE8APmqhrq6pd8f4apfpyw2kytwTRw72zHmHtYQxjw8y2hP6YEUqo3",
        "wallets/sweep",
    ),
    (
        "zprvAdS8rxcvMNey3yQs4Da7heNBzoqJKBHfQCB4cNiksRxv9Qq1M5fboaGva6CvsbK4go79ruWqK9MJqYf8TVwFSqUGF2kBUS4419jbBaNKH1w",
        "wallets/seed2",
    ),
    (
        "zprvawgybbk7jr8gkbyzlvu7qwtwjpihs5upyxvdc5oemfglafvjvcuqyyqtu33p8fk3xq9dcewgidkqasrgnlddygpa9l5sj5v4fmcu5p3ttsn",
        "USER zprv",
    ),
]

DERIVATION_PATHS = [
    ("m/44'/0'/0'/0/0", "m/44'/0'/0'/0/0"),
    ("m/49'/0'/0'/0/0", "m/49'/0'/0'/0/0"),
    ("m/84'/0'/0'/0/0", "m/84'/0'/0'/0/0"),
    ("m/44'/0'/0'/0", "m/44'/0'/0'/0"),
    ("m/49'/0'/0'/0", "m/49'/0'/0'/0"),
    ("m/84'/0'/0'/0", "m/84'/0'/0'/0"),
]

print("=" * 60)
print(f"Testing {len(XPRV_KEYS)} xprv keys")
print("=" * 60)

try:
    from bit import Key

    for xprv, source in XPRV_KEYS:
        for path_name, path in DERIVATION_PATHS:
            try:
                key = Key(xprv)
                derived = key.derive(path)
                addr = derived.address

                if addr in USER_ADDRESSES:
                    print(f"*** MATCH: {source}")
                    print(f"    Path: {path_name}")
                    print(f"    Address: {addr}")

            except:
                pass

    print("\nDone!")

except ImportError:
    print("pip install bit")
