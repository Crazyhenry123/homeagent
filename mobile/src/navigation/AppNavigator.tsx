import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Alert, View} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import type {NavigationContainerRef} from '@react-navigation/native';
import {getToken, clearToken} from '../services/auth';
import {onAuthExpired} from '../services/authEvents';
import {RegisterScreen} from '../screens/RegisterScreen';
import {ConversationListScreen} from '../screens/ConversationListScreen';
import {ChatScreen} from '../screens/ChatScreen';
import {SettingsScreen} from '../screens/SettingsScreen';

export type RootStackParamList = {
  Register: undefined;
  ConversationList: undefined;
  Chat: {conversationId?: string; title?: string};
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function AppNavigator() {
  const [initialRoute, setInitialRoute] = useState<keyof RootStackParamList | null>(null);
  const navigationRef = useRef<NavigationContainerRef<RootStackParamList>>(null);

  useEffect(() => {
    getToken().then(token => {
      setInitialRoute(token ? 'ConversationList' : 'Register');
    });
  }, []);

  // Listen for auth expiration (401 responses)
  useEffect(() => {
    const unsubscribe = onAuthExpired(async () => {
      await clearToken();
      Alert.alert(
        'Session Expired',
        'Please register again with an invite code.',
        [{
          text: 'OK',
          onPress: () => {
            navigationRef.current?.reset({index: 0, routes: [{name: 'Register'}]});
          },
        }],
      );
    });
    return unsubscribe;
  }, []);

  if (!initialRoute) {
    return (
      <View style={{flex: 1, justifyContent: 'center', alignItems: 'center'}}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer ref={navigationRef}>
      <Stack.Navigator initialRouteName={initialRoute}>
        <Stack.Screen
          name="Register"
          component={RegisterScreen}
          options={{headerShown: false}}
        />
        <Stack.Screen
          name="ConversationList"
          component={ConversationListScreen}
          options={{title: 'Chats'}}
        />
        <Stack.Screen
          name="Chat"
          component={ChatScreen}
          options={{title: 'Chat'}}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{title: 'Settings'}}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
